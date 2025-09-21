from specview.sigmf_util import get_annotation_time_bound_relative_to_current_capture

import sigmf
from sigmf import SigMFFile
from specview.app_state import load_capture, smf_get_field_cap_or_global

import numpy as np

def test_get_annotation_time_bound_relative_to_current_capture1(tmpdir):

    TOTAL_NUM_SAMPLES = 2_000_000
    np.zeros(TOTAL_NUM_SAMPLES, dtype=np.complex64).tofile(tmpdir / "data.dat") 

    smf = SigMFFile()
    smf.set_global_field(SigMFFile.DATATYPE_KEY, "cf32_le")
    smf.set_global_field(SigMFFile.SAMPLE_RATE_KEY, 1e6)
    smf.add_capture(start_index=0, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})
    smf.add_capture(start_index=1_000_000, metadata={SigMFFile.FREQUENCY_KEY: 2.4e9})

    smf.set_data_file(str(tmpdir / "data.dat"))

    #smf.add_capture(
    #    {
    #        SigMFFile.FREQUENCY_KEY: 2.4e9,
    #        SigMFFile.START_INDEX_KEY: 0,
    #        SigMFFile.LENGTH_INDEX_KEY: 1_000_000,
    #    }
    #)
    #smf.add_capture(
    #    {
    #        SigMFFile.FREQUENCY_KEY: 2.4e9,
    #        SigMFFile.START_INDEX_KEY: 1_000_000,
    #        SigMFFile.LENGTH_INDEX_KEY: 2_000_000,
    #    }
    #)

    # this annotation is inside the first capture
    smf.add_annotation(start_index= 100_000, length=500_000, metadata={
        SigMFFile.FLO_KEY: 2.4e9-100e3,
        SigMFFile.FHI_KEY: 2.4e9+100e3,
    })

    # this annotation is inside the second capture
    smf.add_annotation(start_index= 1200_000, length=300_000, metadata={
        SigMFFile.FLO_KEY: 2.4e9-100e3,
        SigMFFile.FHI_KEY: 2.4e9+100e3,
    })


    adict = smf.get_annotations()[0]
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=adict, sigmf_file=smf, current_capture_idx=0)
    assert time_bound == (0.1, 0.6)
    # make sure that we don't find this annotation in the second capture
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=adict, sigmf_file=smf, current_capture_idx=1)
    assert time_bound is None

    adict = smf.get_annotations()[1]
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=adict, sigmf_file=smf, current_capture_idx=1)
    assert time_bound == (0.2, 0.5)
    # make sure that we don't find the first annotation inside this capture
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=adict, sigmf_file=smf, current_capture_idx=0)
    assert time_bound is None

    first_capture_idx = 0
    second_capture_idx = 1

    first_annotation = smf.get_annotations()[0]
    second_annotation = smf.get_annotations()[1]

    # unless we turn off the disjoint check
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=second_annotation, sigmf_file=smf, current_capture_idx=first_capture_idx, return_none_if_disjoint=False)
    assert time_bound == ( 1.2, 1.5)

    # unless we turn off the disjoint check
    time_bound = get_annotation_time_bound_relative_to_current_capture(adict=first_annotation, sigmf_file=smf, current_capture_idx=second_capture_idx, return_none_if_disjoint=False)
    assert time_bound == ( -0.9, -0.4)