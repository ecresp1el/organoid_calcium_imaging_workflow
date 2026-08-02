from pathlib import Path

import h5py
import numpy as np
import pytest
import tifffile

from organoid_calcium_imaging_workflow.preprocessing import PreprocessConfig, as_uint16, output_paths, read_imaris_movie, save_projections


def make_ims(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        resolution = handle.create_group("DataSet").create_group("ResolutionLevel 0")
        for index, values in enumerate(([[[1, 2], [3, 4]], [[5, 6], [7, 8]]], [[[10, 20], [30, 40]], [[50, 60], [70, 80]]])):
            channel = resolution.create_group(f"TimePoint {index}").create_group("Channel 0")
            channel.create_dataset("Data", data=np.asarray(values, dtype=np.uint16))


def test_read_imaris_collapses_z_and_sorts_timepoints(tmp_path: Path) -> None:
    ims = tmp_path / "recording.ims"
    make_ims(ims)
    movie = read_imaris_movie(ims)
    np.testing.assert_array_equal(movie, np.array([[[5, 6], [7, 8]], [[50, 60], [70, 80]]], dtype=np.uint16))


def test_read_imaris_rejects_z_stack_without_collapse(tmp_path: Path) -> None:
    ims = tmp_path / "recording.ims"
    make_ims(ims)
    with pytest.raises(ValueError, match="collapsible Z stack"):
        read_imaris_movie(ims, PreprocessConfig(collapse_z=False))


def test_output_layout_and_projection_values(tmp_path: Path) -> None:
    paths = output_paths(tmp_path / "source.ims", tmp_path / "outputs")
    assert paths.raw_tiff == tmp_path / "outputs" / "source" / "raw" / "movie_raw.tif"
    movie = np.array([[[1, 3], [5, 7]], [[2, 4], [6, 8]]], dtype=np.float32)
    save_projections(movie, paths)
    assert tifffile.imread(paths.max_projection).dtype == np.uint16
    assert tifffile.imread(paths.average_projection).dtype == np.uint16
    assert tifffile.imread(paths.std_projection).dtype == np.uint16
    np.testing.assert_array_equal(tifffile.imread(paths.max_projection), np.array([[2, 4], [6, 8]], dtype=np.uint16))
    np.testing.assert_array_equal(tifffile.imread(paths.average_projection), np.array([[2, 4], [6, 8]], dtype=np.uint16))


def test_uint16_conversion_rounds_and_clips() -> None:
    np.testing.assert_array_equal(as_uint16(np.array([-2.0, 1.4, 1.5, 70000.0, np.nan])), np.array([0, 1, 2, 65535, 0], dtype=np.uint16))
