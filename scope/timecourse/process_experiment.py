# This code is licensed under the MIT License (see LICENSE file for details)

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import traceback

import freeimage

def compress_pngs(experiment_root, timepoints=None, level=freeimage.IO_FLAGS.PNG_Z_DEFAULT_COMPRESSION):
    """Recompress image files from an experiment directory.

    Parameters:
        experiment_root: top-level experiment directory
        timepoints: list of timepoints to compress (or list of glob expressions
            to match multiple timepoints). If None, compress all.
        level: flag from freeimage.IO_FLAGS for compression level, or integer
            from 1-9 for compression level.
    """
    for filename in _get_timepoint_files(experiment_root, '*.png', timepoints):
        print('Compressing ', filename)
        image = freeimage.read(filename)
        try:
            with tempfile.NamedTemporaryFile(dir=filename.parent,
                    prefix=filename.stem + 'compressing_', suffix='.png',
                    delete=False) as temp:
                freeimage.write(image, temp.name, flags=level)
            os.replace(temp.name, filename)
        except:
            if temp_name.exists():
                os.unlink(temp.name)
            raise

def compress_main(argv=None):
    parser = argparse.ArgumentParser(description="re-compress image files from experiment")
    parser.add_argument('experiment_root', help='the experiment to compress')
    parser.add_argument('timepoints', nargs="*", metavar='timepoint', help='timepoint(s) to compress')
    parser.add_argument('--level', type=int, default=6, choices=range(1, 10),
        metavar='[1-9]', help="compression level 1-9 (more than 6 doesn't do much)")
    args = parser.parse_args(argv)
    compress_pngs(**args.__dict__)


def segment_images(experiment_root, timepoints, segmenter_path, overwrite_existing=False):
    """Segment image files from an experiment directory.

    Parameters:
        experiment_root: top-level experiment directory
        timepoints: list of timepoints to compress (or list of glob expressions
            to match multiple timepoints). If None, compress all.
        segmenter_path: path to segmentation tool executable
        segmenter_args: arguments, if any, to segmenter. The executable will be
            called as:
                segmenter_path image_list
            where image_list is a file with pairs of lines, where each pair lists
            the path to an image file and then on the next line the path to where
            the mask file should be written.
        overwrite_existing: if False, the segmenter will not be run on existing
            mask files.

    Returns: return code of segmenter executable
    """
    experiment_root = pathlib.Path(experiment_root)
    mask_root = experiment_root / 'derived_data' / 'mask'
    to_segment = []
    for image_file in _get_timepoint_files(experiment_root, 'bf.png', timepoints):
        timepoint = image_file.name.split(' ', 1)[0]
        mask_file = mask_root / image_file.parent / (timepoint + '.png')
        if overwrite_existing or not mask_file.exists():
            mask_file.parent.mkdir(exist_ok=True, parents=True)
            to_segment.append((image_file, mask_file))
    with tempfile.NamedTemporaryFile(dir=experiment_root, prefix='to_segment_', delete=False) as temp:
        for image_file, mask_file in to_segment:
            temp.write(str(image_file)+'\n')
            temp.write(str(mask_file)+'\n')
    returncode = subprocess.call([segmenter_path, temp.name])
    os.unlink(temp.name)
    return returncode

def segment_main(argv=None):
    parser = argparse.ArgumentParser(description="re-compress image files from experiment")
    parser.add_argument('experiment_root', help='the experiment to segment')
    parser.add_argument('segmenter_path', help='path to segmentation executable')
    parser.add_argument('timepoints', nargs="*", metavar='timepoint', help='timepoint(s) to segment')
    parser.add_argument('--overwrite', dest='overwrite_existing', action='store_true',
        help="don't skip existing masks")
    args = parser.parse_args(argv)
    segment_images(**args.__dict__)


def _get_timepoint_files(experiment_root, file_match, timepoints=None):
    """Generate a list of files to process from all positions.

    Timepoint files are saved as '{timepoint} {image_type}.{ext}'. The file_match
    parameter should be a glob or literal expression that matches the desired
    '{image_type}.{ext}' portion of the name. The timepoints parameter specifies
    a list of glob or literal expressions to match the '{timepoint}' portion of
    the name. If not specified, or None or empty list, all timepoints will be
    matched.
    """
    experiment_root = pathlib.Path(experiment_root)
    if not timepoints: # timepoints is None or empty list/string
        timepoints = ['*']
    for position_root in sorted(p.parent for p in experiment_root.glob('*/position_metadata.json')):
        for timepoint in timepoints:
            yield from sorted(position_root.glob(timepoint + ' ' + file_match))


def run_in_background(function, *args, logfile=None, nice=None, delete_logfile=True, **kws):
    """Run a function in a background process (by forking the foreground process)

    Parameters:
        function: function to run.
        *args: arguments to function.
        logfile: if not None, redirect stderr and stdout to this file. The file
            will be opened in append mode (so existing logs will be added to)
            and the PID of the background process will be written to the file
            before running the function.
        nice: if not None, level to renice the forked process to.
        delete_logfile: if True, the logfile will be deleted after the function
            exits, except in case of an exception, where the file will be retained
            to aid in debugging. (It will contain the traceback information.)
        **kws: keyword arguments to function.
    """
    if _detach_process_context():
        # _detach_process_context returns True in the parent process and False
        # in the child process.
        return
    try:
        if logfile is None:
            log = None
            delete_logfile = False
        else:
            logfile = pathlib.Path(logfile)
            log = logfile.open('a')
            log.write(str(os.getpid())+'\n')
        # close standard streams so the process can still run even if the
        # controlling terminal window is closed.
        _redirect_stream(sys.stdin, None)
        _redirect_stream(sys.stdout, log)
        _redirect_stream(sys.stderr, log)
        if nice is not None:
            os.nice(nice)
        function(*args, **kws)
    except:
        # don't remove the logfile...
        traceback.print_exc()
        delete_logfile = False
    finally:
        log.close()
        if delete_logfile:
            logfile.unlink()
        # if we don't exit with os._exit(), then if this function was called from
        # ipython, the child will try to return back to the ipython shell, with all
        # manner of hilarity ensuing.
        os._exit(0)

def _detach_process_context():
    """Detach the process context from parent and session.

    Detach from the parent process and session group, allowing the parent to
    keep running while the child continues running. Uses the standard UNIX
    double-fork strategy to isolate the child.
    """
    if _fork_carefully() > 0:
        # parent: return now
        return True
    # child: fork again
    os.setsid()
    if _fork_carefully() > 0:
        # exit parent
        os._exit(0)
    return False

def _fork_carefully():
    try:
        return os.fork()
    except OSError as e:
        raise RuntimeError('Fork failed: [{}] {}'.format(e.errno, e.strerror))

def _redirect_stream(src, dst):
    if dst is None:
        dst_fd = os.open(os.devnull, os.O_RDWR)
    else:
        dst_fd = dst.fileno()
    os.dup2(dst_fd, src.fileno())