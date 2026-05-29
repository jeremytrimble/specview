from sigmf import SigMFFile
import numpy as np
from pathlib import Path
import sigmf

from specview.loaded_file_mgmt import LoadedAnnotationDict, LoadedCaptureDict, LoadedDictAction, LoadedFile, LoadedFileAction, LoadedFilesCollection, CacheManager, FileID, CaptureID, AnnotationID


def generate_example_sigmffile(tmpdir) -> Path:

    TOTAL_NUM_SAMPLES = 2_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "example.sigmf-data") 

    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    smf.add_capture(start_index=1_000_000, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})

    smf.set_data_file(str(tmpdir / "example.sigmf-data"))

    smf.add_annotation(start_index= 100_000, length=500_000, metadata={
        SigMFFile.FLO_KEY: 2.4e9-100e3,
        SigMFFile.FHI_KEY: 2.4e9+100e3,
    })

    smf.add_annotation(start_index= 1200_000, length=300_000, metadata={
        SigMFFile.FLO_KEY: 2.4e9-100e3,
        SigMFFile.FHI_KEY: 2.4e9+100e3,
    })

    smf.tofile(tmpdir / "example.sigmf-meta")

    return Path(tmpdir / "example.sigmf-meta")

def test_loaded_files_collection(tmpdir):

    sigmf_path = generate_example_sigmffile(tmpdir)

    acc_callbacks = []
    def annotation_changed_callback(annotationid: AnnotationID, action:LoadedDictAction):
        acc_callbacks.append((annotationid, action))

    load_callbacks = []
    def load_callback(file: LoadedFile, action:LoadedFileAction):
        load_callbacks.append((file, action))

    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lfc.set_annotation_changed_callback( annotation_changed_callback )
    lfc.set_file_load_or_unload_callback( load_callback )

    lf = lfc.load_file(sigmf_path)

    assert len(lfc.loaded_file_dict) == 1
    assert lf._file_id in lfc.loaded_file_dict
    assert not lf.has_unsaved_changes

    annotation_ids = lf.get_annotations_dict().keys()
    assert set(annotation_ids) == set( ann_id for (ann_id, action) in acc_callbacks )

    assert len(acc_callbacks) == 2
    for annotationid, action in acc_callbacks:
        assert action == LoadedDictAction.LOADED

    assert lf is lfc.get_loaded_file_from_id(lf._file_id)

    assert len(lfc._annotation_id_to_annotations) == 2

    assert len(load_callbacks) == 1
    assert load_callbacks == [(lf._file_id, LoadedFileAction.OPENED)]

    # add an annotation
    md = {
        SigMFFile.FLO_KEY: 2.4e9-50e3,
        SigMFFile.FHI_KEY: 2.4e9+50e3,
        SigMFFile.LABEL_KEY: "New Signal",
    }
    added_annotation_dict = lf.add_annotation( start_index=123_456, length=1_000, metadata=md)
    assert lf.has_unsaved_changes

    assert len(lf.get_annotations_dict()) == 3
    assert len(acc_callbacks) == 3
    most_recent_cb = acc_callbacks[-1]
    ann_id, action = most_recent_cb
    assert ann_id == added_annotation_dict.annotation_id
    assert action == LoadedDictAction.ADDED
    assert added_annotation_dict is lf.get_annotations_dict()[ann_id]

    assert set(added_annotation_dict.keys()) == set([
        SigMFFile.START_INDEX_KEY,
        SigMFFile.LENGTH_INDEX_KEY,
        SigMFFile.FLO_KEY,
        SigMFFile.FHI_KEY,
        SigMFFile.LABEL_KEY,
    ])

    assert len(lfc._annotation_id_to_annotations) == 3

    # TODO: save here
    lf.save()
    assert not lf.has_unsaved_changes

    added_annotation_dict["my_new_field"] = 42
    assert len(acc_callbacks) == 4
    
    del added_annotation_dict, ann_id, action, most_recent_cb, annotation_ids, md

    # delete an annotation
    ann_id_to_delete = sorted(lf.get_annotations_dict().keys())[0]
    ann_to_delete = lfc.get_annotation_from_id(ann_id_to_delete)
    assert ann_to_delete is not None
    ann_to_delete.delete_annotation()

    assert lf.has_unsaved_changes

    most_recent_cb = acc_callbacks[-1]
    ann_id, action = most_recent_cb
    assert ann_id == ann_id_to_delete
    assert action == LoadedDictAction.DELETED

    assert len(lfc._annotation_id_to_annotations) == 2

    lfc.close_file(lf._file_id)

    assert len(lfc.loaded_file_dict) == 0
    assert len(load_callbacks) == 2
    assert load_callbacks[-1] == (lf._file_id, LoadedFileAction.CLOSED)

    assert len(lfc._annotation_id_to_annotations) == 0
    assert len(lfc._capture_id_to_capture) == 0

    smf = sigmf.sigmffile.fromfile(sigmf_path)
    assert len(smf.get_annotations()) == 3 # original file had 2, we added one and saved (and did not save again after deletion)


def test_capture_frequency_defaulting(tmpdir):
    """Test that missing capture frequency fields are defaulted to 0 Hz."""
    TOTAL_NUM_SAMPLES = 1_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "test.sigmf-data")
    
    # Create a SigMF file with a capture that is missing the frequency field
    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)
    
    # Add a capture without frequency field by directly manipulating the metadata
    capture_metadata = {SigMFFile.START_INDEX_KEY: 0}
    # Deliberately omit SigMFFile.FREQUENCY_KEY
    smf._metadata[SigMFFile.CAPTURE_KEY] = [capture_metadata]
    
    smf.set_data_file(str(tmpdir / "test.sigmf-data"))
    smf.tofile(tmpdir / "test.sigmf-meta")
    
    # Load the file through LoadedFilesCollection
    cache_manager = CacheManager(base_path=Path(tmpdir/"cache"))
    lfc = LoadedFilesCollection(cache_manager=cache_manager)
    lf = lfc.load_file(Path(tmpdir / "test.sigmf-meta"))
    
    # Verify the file was loaded
    assert lf is not None
    
    # Get the capture and verify frequency was defaulted to 0 Hz
    captures = lf._capture_id_to_capture
    assert len(captures) == 1
    
    capture = list(captures.values())[0]
    assert capture.center_freq_Hz == 0.0
    
    # Also verify the underlying SigMF file has the frequency field set
    assert SigMFFile.FREQUENCY_KEY in capture
    assert capture[SigMFFile.FREQUENCY_KEY] == 0.0
