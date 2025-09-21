import sigmf

def get_annotation_time_bound_relative_to_current_capture(adict: dict, current_capture_idx:int, sigmf_file: sigmf.SigMFFile, return_none_if_disjoint:bool=True ) -> tuple[float,float]|None:

    ann_start_idx = adict.get(sigmf.SigMFFile.START_INDEX_KEY)
    ann_length_samples = adict.get(sigmf.SigMFFile.LENGTH_INDEX_KEY)

    if ann_start_idx is None or ann_length_samples is None:
        return None

    ann_start_idx = int(ann_start_idx)
    ann_length_samples = int(ann_length_samples)

    if ann_start_idx < 0 or ann_length_samples <= 0:
        return None

    sample_rate_Hz = sigmf_file.get_global_field(sigmf.SigMFFile.SAMPLE_RATE_KEY)
    if sample_rate_Hz is None:
        raise ValueError("Global SAMPLE_RATE_KEY not found in SigMF file.")

    # Get the start index from the annotation dictionary or the capture
    captures_array = sigmf_file.get_captures()
    cdict = captures_array[current_capture_idx]
    # Note: LENGTH_INDEX_KEY is only defined in annotations, never in captures
    # Note: START_INDEX_KEY is REQUIRED in all captures
    capture_start_idx = cdict[sigmf.SigMFFile.START_INDEX_KEY]

    if current_capture_idx + 1 < len(captures_array):
        next_cdict = captures_array[current_capture_idx + 1]
        capture_end_idx = next_cdict[sigmf.SigMFFile.START_INDEX_KEY]
        del next_cdict
    else:
        capture_end_idx = sigmf_file.sample_count   # this is the total number of samples in the data file
    capture_duration_sec = (capture_end_idx - capture_start_idx) / sample_rate_Hz
    if capture_duration_sec <= 0:
        raise ValueError("Capture has non-positive duration.")

    samples_from_beginning_of_capture = ann_start_idx - capture_start_idx

    start_time_sec = samples_from_beginning_of_capture / sample_rate_Hz
    end_time_sec = (samples_from_beginning_of_capture + ann_length_samples) / sample_rate_Hz

    if return_none_if_disjoint:
        # if both start and end are before the capture start, or both are after the capture end, then return None
        if end_time_sec < 0 and start_time_sec < 0:
            return None
        if start_time_sec > capture_duration_sec and end_time_sec > capture_duration_sec:
            return None

    return start_time_sec, end_time_sec