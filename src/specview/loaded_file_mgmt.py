from __future__ import annotations

import typing
from pathlib import Path
import enum
import sigmf

import random
rnd = random.Random(42)

# These ids are unique within one run of the application, for internal use only
#FileID = typing.NewType("FileID", str)
#CaptureID = typing.NewType("CaptureID", str)
#AnnotationID = typing.NewType("AnnotationID", str)

# Type aliases:
FileID = str
CaptureID = str
AnnotationID = str


class LoadedThingCounter:
    def __init__(self, prefix:str):
        self._counter:int =0
        self._prefix = prefix
    def get_next_id(self) -> str:
        rv = f"{self._prefix}{self._counter:03d}"
        self._counter += 1
        return rv

loaded_file_counter = LoadedThingCounter(prefix="fid")
loaded_capture_counter = LoadedThingCounter(prefix="cap")
loaded_annotation_counter = LoadedThingCounter(prefix="ann")

del LoadedThingCounter

class LoadedFileAction(enum.Enum):
    OPENED = "opened"
    CLOSED = "closed"
    # TODO: should "saved" be an action here?

class LoadedDictAction(enum.Enum):
    LOADED = "loaded"       # the annotation was loaded from the file initially
    ADDED = "added"         # the annotation was added (newly created)
    MODIFIED = "modified"   # the annotation was changed
    DELETED = "deleted"     # the annotation was deleted (removed from the parent file)
    CLOSED = "closed"       # the parent file was closed, so this annotation is no longer valid

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"LoadedDictAction.{self.value.upper()}"

# TODO: put this somewhere
#        annotation_dict = self._id_to_annotation.get(annotation_id)
#        if annotation_dict is not None:
#            app_state: AppState = QApplication.instance().app_state
#            app_state.annotation_changed.emit(self._open_file_id, annotation_dict, action)


class LoadedFilesCollection:
    """
    A class representing a collection of loaded SigMF files, their LoadedCaptureDict, and LoadedAnnotationDict objects.
    """
    def __init__(self):

        # mapping of all known file IDs to their LoadedFile objects
        #  this mapping is maintained by this LoadedFilesCollection class
        self._fileid_to_loadedfile: dict[FileID, LoadedFile] = {}

        # mapping of all known capture IDs to their LoadedCaptureDict objects
        #  this mapping is maintained by the LoadedFile class
        self._capture_id_to_capture: dict[CaptureID, LoadedCaptureDict] = {}

        # mapping of all known annotation IDs to their LoadedAnnotationDict objects
        #  this mapping is maintained by the LoadedFile class
        self._annotation_id_to_annotations: dict[AnnotationID, LoadedAnnotationDict] = {}

        self._annotation_changed_cb: typing.Callable[[AnnotationID, LoadedDictAction], None]|None = None
        self._file_load_or_unload_cb: typing.Callable[[FileID, LoadedFileAction], None]|None = None

    def set_file_load_or_unload_callback(self, cb: typing.Callable[[FileID, LoadedFileAction], None]) -> None:
        self._file_load_or_unload_cb = cb

    def set_annotation_changed_callback(self, cb: typing.Callable[[AnnotationID, LoadedDictAction], None]) -> None:
        self._annotation_changed_cb = cb

    def load_file(self, file_path: Path) -> LoadedFile:
        loaded_file = LoadedFile(file_path=file_path, parent_loaded_files=self)
        self._fileid_to_loadedfile[loaded_file._file_id] = loaded_file
        if self._file_load_or_unload_cb is not None:
            self._file_load_or_unload_cb(loaded_file._file_id, LoadedFileAction.OPENED)
        return loaded_file

    @property
    def loaded_file_dict(self):     # TODO: remove me in favor of get_loaded_file_from_id()
        return self._fileid_to_loadedfile

    def get_loaded_file_from_id(self, loaded_file_id:FileID) -> LoadedFile|None:
        return self._fileid_to_loadedfile.get(loaded_file_id)

    def get_capture_from_id(self, capture_id:CaptureID) -> LoadedCaptureDict|None:
        return self._capture_id_to_capture.get(capture_id)

    def get_annotation_from_id(self, annotation_id:AnnotationID) -> LoadedAnnotationDict|None:
        return self._annotation_id_to_annotations.get(annotation_id)

    def _on_child_annotation_changed(self, annotation_id:AnnotationID, action:LoadedDictAction) -> None:
        if self._annotation_changed_cb is not None:
            self._annotation_changed_cb(annotation_id, action)

    def close_file(self, fileid: FileID):
        if fileid in self._fileid_to_loadedfile:
            loaded_file = self._fileid_to_loadedfile[fileid]
            loaded_file.close()
            del self._fileid_to_loadedfile[fileid]
            if self._file_load_or_unload_cb is not None:
                self._file_load_or_unload_cb(fileid, LoadedFileAction.CLOSED)
        else:
            # TODO: should this raise an exception or just do nothing?
            raise ValueError(f"File ID {fileid} not found in loaded files.")

class LoadedAnnotationDict(dict):
    """
    A dictionary-like object that represents an annotation loaded from a SigMF file.
    It is tied to a parent LoadedFile and notifies it when the annotation is modified.
    It also provides a method to create a new annotation dictionary, which is
    not intended to be used directly, but rather through the LoadedFile's
    add_annotation method which returns an instance of this class.
    """
    @classmethod
    def create_annotation_dict(cls, parent_loadedfile: LoadedFile, annotation_id:AnnotationID, annotation_content:dict) -> LoadedAnnotationDict:
        # TODO: don't instantiate a second dictionary -- rather, wrap the existing dictionary with methods that access the underlying
        rv = cls(annotation_content)
        rv._parent_loadedfile = parent_loadedfile
        rv._annotation_id = annotation_id
        rv._deactivated = False
        return rv

    @property
    def parent_loadedfile(self) -> LoadedFile:
        return self._parent_loadedfile
    
    def _notify_parent_that_i_was_modified(self):
        if self._parent_loadedfile is not None:
            self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.MODIFIED)

    def __setitem__(self, key, value):
        rv = super().__setitem__(key, value)
        self._notify_parent_that_i_was_modified()
        return rv
    
    def __delitem__(self, key):
        rv = super().__delitem__(key)
        self._notify_parent_that_i_was_modified()
        return rv   

    def update(self, *args, **kwargs):
        rv = super().update(*args, **kwargs)
        self._notify_parent_that_i_was_modified()
        return rv

    def pop(self, key, *args):
        rv = super().pop(key, *args)
        self._notify_parent_that_i_was_modified()
        return rv
    
    def clear(self):
        rv = super().clear()
        self._notify_parent_that_i_was_modified()
        return rv   

    def delete_annotation(self):
        if not self._deactivated:
            self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.DELETED)
            self._parent_loadedfile = None
        self._deactivated = True

    def close_annotation(self):
        if not self._deactivated:
            self._parent_loadedfile._on_child_annotation_changed(self._annotation_id, LoadedDictAction.CLOSED)
            self._parent_loadedfile = None
        self._deactivated = True

    @property
    def annotation_id(self) -> AnnotationID:
        return self._annotation_id

    def get_frequency_range_Hz(self) -> tuple[float,float]|None:
        f_lo = self.get(sigmf.SigMFFile.FLO_KEY)
        f_hi = self.get(sigmf.SigMFFile.FHI_KEY)
        if f_lo is not None and f_hi is not None:
            return (float(f_lo), float(f_hi))
        else:
            return None
    
    def get_time_range_relative_to_capture(self, capture_idx:int) -> tuple[float,float]|None:
        return get_annotation_time_bound_relative_to_current_capture(self, capture_idx, self._parent_loadedfile.sigmf_file)

    @property
    def label(self) -> str:
        label = self.get("label")
        if label is None:
            return ""
        else:
            return str(label)


class LoadedFile:
    """
    A class representing a loaded SigMF file.
    It contains the file path, the SigMFFile object, and a dictionary of annotations.
    It also provides methods to add annotations and get the annotations.
    It emits signals when annotations are added, modified, or deleted.
    """
    def __init__(self, file_path: Path, parent_loaded_files: LoadedFilesCollection):
        # Note: file_path is the path to the .sigmf-meta file
        # sigmf_file is the SigMFFile object loaded from that file
        self._parent_loaded_files = parent_loaded_files

        self._sigmf_file: sigmf.SigMFFile = sigmf.sigmffile.fromfile(file_path)
        self._has_unsaved_changes = False
        self._file_path: Path = Path(self._sigmf_file.data_file)  # This is the path to the .sigmf-data file
        self._file_id: FileID = loaded_file_counter.get_next_id()

        self._capture_id_to_capture: dict[CaptureID, LoadedAnnotationDict] = {}
        self._annotation_id_to_annotation: dict[AnnotationID, LoadedAnnotationDict] = {}

        self._captures: list[LoadedCaptureDict] = []
        for cap_idx, cap_dict in enumerate(self._sigmf_file.get_captures()):
            capture_id = self._get_next_capture_id()
            lcd = LoadedCaptureDict.create_capture_dict(parent_loadedfile=self, capture_idx=cap_idx, capture_id=capture_id, capture_content=cap_dict)
            self._captures.append(lcd)
            self._parent_loaded_files._capture_id_to_capture[capture_id] = lcd  # store in the global mapping

        for annotation_dict in self._sigmf_file.get_annotations():
            annotation_id = self._get_next_annotation_id()
            lad = LoadedAnnotationDict.create_annotation_dict(parent_loadedfile=self, annotation_id=annotation_id, annotation_content=annotation_dict)
            self._annotation_id_to_annotation[annotation_id] = lad
            self._parent_loaded_files._annotation_id_to_annotations[annotation_id] = lad  # store in the global mapping

        for annotation_id in self._annotation_id_to_annotation:
            self._on_child_annotation_changed(annotation_id, LoadedDictAction.LOADED)

    @property
    def sigmf_file(self) -> sigmf.SigMFFile:
        return self._sigmf_file

    @property
    def has_unsaved_changes(self) -> bool:
        return self._has_unsaved_changes

    def save(self):
        self._sigmf_file.tofile(self._file_path.with_suffix(".sigmf-meta"))
        self._has_unsaved_changes = False

    # TODO: support save-as?

    @property
    def file_path(self) -> Path:
        return self._file_path

    @property
    def file_id(self) -> FileID:
        return self._file_id

    def _on_child_annotation_changed(self, annotation_id:AnnotationID, action:LoadedDictAction) -> None:
        """
        Called when one of our children annotations has changed.
        Emits the annotation_changed signal with the file ID and the set of changed annotations.
        """
        self._parent_loaded_files._on_child_annotation_changed(annotation_id, action)
        if action in (LoadedDictAction.ADDED, LoadedDictAction.DELETED, LoadedDictAction.MODIFIED):
            self._has_unsaved_changes = True
        
        if action in (LoadedDictAction.DELETED, LoadedDictAction.CLOSED):
            self._annotation_id_to_annotation.pop(annotation_id, None) # remove from our own mapping
            self._parent_loaded_files._annotation_id_to_annotations.pop(annotation_id, None) # remove from the global mapping

    def _get_next_capture_id(self) -> CaptureID:
        """
        Returns the next capture ID, in a global namespace.
        """
        return loaded_capture_counter.get_next_id()

    def _get_next_annotation_id(self) -> AnnotationID:
        """
        Returns the next annotation ID, in a global namespace.
        """
        return loaded_annotation_counter.get_next_id()

    def _add_and_return_annotation_dict(self, start_index:int, length:int|None=None, metadata:dict|None=None) -> dict:
        # HACK: sigmf doesn't return the annotation dict back to us, so we have
        # to "mark" it in a way that we can find after insertion and sorting.
        # Longer-term, maybe we need to write our own sigmf file implementation...

        INSERTION_MARKER_KEY = "_specview_insertion_marker"
        INSERTION_MARKER_VALUE = rnd.randint(0,1000000)
        metadata = dict(metadata)
        metadata[INSERTION_MARKER_KEY] = INSERTION_MARKER_VALUE
        self._sigmf_file.add_annotation(start_index=start_index, length=length, metadata=metadata)

        annotation_list = self._sigmf_file.get_annotations()
        annotation_dict = None
        for ad in annotation_list:
            if ad.get(INSERTION_MARKER_KEY) == INSERTION_MARKER_VALUE:
                # found it
                del ad[INSERTION_MARKER_KEY]
                annotation_dict = ad
                break
        if annotation_dict is None:
            # this shouldn't happen
            raise ValueError("Failed to find newly added annotation in SigMF file.")
        return annotation_dict

    def add_annotation(self, start_index:int, length:int|None=None, metadata:dict|None=None) -> LoadedAnnotationDict:
        """
        Add a new annotation to this file.
        Returns the AnnotationDict for the new annotation.
        """
        annotation_dict = self._add_and_return_annotation_dict(start_index=start_index, length=length, metadata=metadata)

        annotation_id = self._get_next_annotation_id()
        new_annotation = LoadedAnnotationDict.create_annotation_dict(self, annotation_id, annotation_dict)
        self._annotation_id_to_annotation[annotation_id] = new_annotation
        self._parent_loaded_files._annotation_id_to_annotations[annotation_id] = new_annotation  # store in the global mapping
        self._on_child_annotation_changed(annotation_id, LoadedDictAction.ADDED)
        return new_annotation

    def get_annotations_dict(self) -> dict[str, LoadedAnnotationDict]:
        """
        Returns a dictionary of annotations for this file.
        The keys are the annotation IDs and the values are the LoadedAnnotationDict objects.
        """
        return dict(self._annotation_id_to_annotation)

    def _close_annotations(self) -> None:
        all_annotations = list(self._annotation_id_to_annotation.values())
        for ad in all_annotations:
            ad.close_annotation()

    def close(self) -> None:
        self._close_annotations()
        self._sigmf_file = None
        for cap in self._captures:
            del self._parent_loaded_files._capture_id_to_capture[cap.capture_id]

class LoadedCaptureDict(dict):
    @classmethod
    def create_capture_dict(cls, parent_loadedfile: LoadedFile, capture_idx:int, capture_id:CaptureID, capture_content:dict) -> LoadedCaptureDict:
        # TODO: don't instantiate a second dictionary -- rather, wrap the existing dictionary with methods that access the underlying
        rv = cls(capture_content)
        rv._parent_loadedfile = parent_loadedfile
        rv._capture_idx = capture_idx
        rv._capture_id = capture_id
        return rv

    @property
    def parent_loadedfile(self) -> LoadedFile:
        return self._parent_loadedfile

    @property
    def capture_id(self) -> CaptureID:
        return self._capture_id

    @property
    def capture_idx_in_file(self) -> int:
        return self._capture_idx