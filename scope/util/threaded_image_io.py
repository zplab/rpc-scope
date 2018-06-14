# This code is licensed under the MIT License (see LICENSE file for details)

import concurrent.futures as futures
import freeimage

class COMPRESSION:
    DEFAULT = 0 # save TIFFs using FreeImage default LZW compression, and PNGs with ZLib level 6 compression

    PNG_NONE = freeimage.IO_FLAGS.PNG_Z_NO_COMPRESSION # save without compression
    PNG_FAST = freeimage.IO_FLAGS.PNG_Z_BEST_SPEED # save using ZLib level 1 compression flag
    PNG_BEST = freeimage.IO_FLAGS.PNG_Z_BEST_COMPRESSION # save using ZLib level 9 compression flag

    TIFF_NONE = freeimage.IO_FLAGS.TIFF_NONE # save without compression


class ThreadedIO:
    def __init__(self, num_threads):
        self.threadpool = futures.ThreadPoolExecutor(num_threads)

    def write(self, images, paths, flags=0, wait=True):
        """Write out a list of images to the given paths. If wait is True,
        wait until all jobs are done and then return (or raise an error if
        the jobs raised an error). Otherwise, return a list of futures representing
        the jobs, which the user can wait on when desired.
        """
        futures_out = [self.threadpool.submit(freeimage.write, image, str(path), flags) for image, path in zip(images, paths)]
        if wait:
            self.wait(futures_out)
        else:
            return futures_out

    @staticmethod
    def wait(futures_out):
        """Wait until all the provided futures have completed; raise an error if
        one or more error out."""
        # wait until all have completed or errored out
        futures.wait(futures_out)
        # now get the result() from each future, which will raise any errors encountered
        # during the execution.
        # The futures.wait() call above makes sure that everything that doesn't
        # error out has a chance to finish before we barf an exception.
        [f.result() for f in futures_out]


    def read(self, paths):
        """Return an iterator over image arrays read from the given paths."""
        paths = map(str, paths)
        return self.threadpool.map(freeimage.read, paths)
