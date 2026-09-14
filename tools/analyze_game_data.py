#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
from dataclasses import dataclass
import argparse
import hashlib
import struct

RESOURCE_SIGNATURE = b"PARTOUT(4.0)RESOURCE"
HEADER_FMT = "<21s50s100siHiH"
VARIABLE_SIZE = -1
ZERO_SIZE = 0

@dataclass(frozen=True)
class FieldSpec:
    name: str
    size: int

FIELD_SPECS = [
    FieldSpec("unknown_0", 2),
    FieldSpec("bitmap", VARIABLE_SIZE),
    FieldSpec("unknown_2", 2),
    FieldSpec("group_name", VARIABLE_SIZE),
    FieldSpec("unknown_4", VARIABLE_SIZE),
    FieldSpec("unknown_5", VARIABLE_SIZE),
    FieldSpec("unknown_6", VARIABLE_SIZE),
    FieldSpec("unknown_7", VARIABLE_SIZE),
    FieldSpec("unknown_8", VARIABLE_SIZE),
    FieldSpec("unknown_9", VARIABLE_SIZE),
    FieldSpec("unknown_10", VARIABLE_SIZE),
    FieldSpec("unknown_11", VARIABLE_SIZE),
    FieldSpec("zmap", VARIABLE_SIZE),
    FieldSpec("terminator", ZERO_SIZE),
]
BITMAP_FIELD = 1
GROUP_NAME_FIELD = 3
ZMAP_FIELD = 12

def require_range(data: bytes, offset: int, size: int, label: str):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label}: truncated data at offset {offset}, need {size} bytes")

def parse_dat(path: Path):
    data=path.read_bytes(); header_size=struct.calcsize(HEADER_FMT)
    require_range(data,0,header_size,"header")
    sig,app,desc,file_size,groups,body_size,unknown=struct.unpack_from(HEADER_FMT,data,0)
    if not sig.startswith(RESOURCE_SIGNATURE): raise ValueError("not a PARTOUT(4.0)RESOURCE file")
    off=header_size+unknown; require_range(data,off,0,"body")
    field_counts=Counter(); resolutions=Counter(); flags=Counter(); dims=Counter()
    bitmap_payload=zmap_payload=0; max_bitmap=None; names={}; bitmap_rows=[]
    for gi in range(groups):
        require_range(data,off,1,f"group {gi} entry count"); entry_count=data[off]; off+=1
        for _ in range(entry_count):
            require_range(data,off,1,f"group {gi} field type"); et=data[off]; off+=1
            if et >= len(FIELD_SPECS): raise ValueError(f"group {gi}: unknown field type {et}")
            spec=FIELD_SPECS[et]; fixed=spec.size
            if fixed>=0: size=fixed
            else:
                require_range(data,off,4,f"group {gi} {spec.name} size")
                size=struct.unpack_from("<I",data,off)[0]; off+=4
            field_counts[et]+=1
            if et==BITMAP_FIELD:
                require_range(data,off,14,f"group {gi} bitmap header")
                res,w,h,x,y,payload,fl=struct.unpack_from("<BhhhhiB",data,off); off+=14
                require_range(data,off,payload,f"group {gi} bitmap payload")
                resolutions[res]+=1; flags[fl]+=1; dims[(w,h)]+=1; bitmap_payload+=payload
                bitmap_rows.append((gi,res,w,h,x,y,payload,fl)); area=w*h
                if max_bitmap is None or area>max_bitmap[0]: max_bitmap=(area,gi,w,h,x,y,payload,fl)
                off+=payload
            elif et==ZMAP_FIELD:
                require_range(data,off,14,f"group {gi} zmap header")
                w,h,stride,unk0,u10,u11=struct.unpack_from("<hhhihh",data,off); off+=14
                payload=size-14
                if payload<0: raise ValueError(f"group {gi}: invalid zmap size {size}")
                require_range(data,off,payload,f"group {gi} zmap payload"); zmap_payload+=payload; off+=payload
            else:
                require_range(data,off,size,f"group {gi} {spec.name}")
                payload=data[off:off+size]
                if et==GROUP_NAME_FIELD: names[gi]=payload.split(b"\0",1)[0].decode("latin1","replace")
                off+=size
    print(f"file={path}"); print(f"sha256={hashlib.sha256(data).hexdigest()}")
    print(f"app={app.rstrip(bytes([0])).decode('latin1','replace')}")
    print(f"description={desc.rstrip(bytes([0])).decode('latin1','replace')}")
    print(f"bytes={len(data)} groups={groups} parsed_bytes={off}")
    print(f"field_counts={dict(sorted(field_counts.items()))}")
    print(f"bitmap_count={sum(resolutions.values())} bitmap_resolutions={dict(sorted(resolutions.items()))}")
    print(f"bitmap_payload_bytes={bitmap_payload} zmap_payload_bytes={zmap_payload}")
    if max_bitmap:
        area,gi,w,h,x,y,payload,fl=max_bitmap
        print(f"largest_bitmap=group:{gi} name:{names.get(gi,'')} size:{w}x{h} pos:{x},{y} payload:{payload} flags:{fl}")
    print("widest_bitmaps:")
    for gi,res,w,h,x,y,payload,fl in sorted(bitmap_rows,key=lambda r:r[2],reverse=True)[:10]:
        print(f"  group={gi:3d} name={names.get(gi,'')!r:18s} res={res} {w}x{h} at {x},{y} payload={payload} flags={fl}")

def parse_bmp(path: Path):
    data=path.read_bytes(); require_range(data,0,34,"BMP header")
    if data[:2]!=b"BM": raise ValueError("not BMP")
    off=struct.unpack_from("<I",data,10)[0]; w=struct.unpack_from("<i",data,18)[0]; h=struct.unpack_from("<i",data,22)[0]
    bpp=struct.unpack_from("<H",data,28)[0]; comp=struct.unpack_from("<I",data,30)[0]
    print(f"file={path}"); print(f"sha256={hashlib.sha256(data).hexdigest()}"); print(f"bytes={len(data)} bmp={w}x{h} bpp={bpp} compression={comp} pixel_offset={off}")

def main():
    ap=argparse.ArgumentParser(description="Inspect Space Cadet resource files without modifying them.")
    ap.add_argument("path",type=Path); args=ap.parse_args(); paths=[]
    if args.path.is_dir():
        for name in ("PINBALL.DAT","FONT.DAT","table.bmp"):
            q=args.path/name
            if q.exists(): paths.append(q)
    else: paths=[args.path]
    for i,path in enumerate(paths):
        if i: print("\n---")
        try: parse_bmp(path) if path.suffix.lower()==".bmp" else parse_dat(path)
        except Exception as exc: print(f"{path}: ERROR: {exc}")

if __name__=="__main__": main()
