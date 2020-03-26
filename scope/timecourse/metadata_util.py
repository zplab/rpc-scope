import pathlib
import json

def get_experiment_metadata(experiment_root):
    experiment_root = pathlib.Path(experiment_root)
    experiment_metadata_path = experiment_root / 'experiment_metadata.json'
    with experiment_metadata_path.open('r') as f:
        experiment_metadata = json.load(f)
    return experiment_metadata_path, experiment_metadata

def get_position_metadata(experiment_root, position_name):
    experiment_root = pathlib.Path(experiment_root)
    position_dir = experiment_root / position_name
    metadata_path = position_dir / 'position_metadata.json'
    if metadata_path.exists():
        with metadata_path.open('r') as f:
            position_metadata = json.load(f)
    else:
        position_metadata = []
    return position_dir, metadata_path, position_metadata

def get_latest_coordinates(position_name, experiment_metadata, position_metadata, ignore_autofocus_z=False):
    x, y, z = experiment_metadata['positions'][position_name]
    if not ignore_autofocus_z:
        # see if we have an updated z position to use on...
        for timepoint_metadata in position_metadata[::-1]:
            if 'fine_z' in timepoint_metadata:
                z = timepoint_metadata['fine_z']
                break
    return x, y, z
