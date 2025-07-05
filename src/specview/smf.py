import sigmf
import typing

UNDEF = object()

def smf_get_field_cap_or_global(smf: sigmf.SigMFFile, capture_idx:int|None, field:str, default:typing.Any|typing.Literal[UNDEF]=UNDEF) -> typing.Any:
    if capture_idx is not None:
        cap = smf.get_captures()[capture_idx]
        if field in cap:
            return cap[field]
    val = smf.get_global_field(field, default=default)
    if val is UNDEF:
        raise KeyError(f"can't find value for field {field} in capture {capture_idx} or globals")
    else:
        return val