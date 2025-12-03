#!/usr/bin/env python3
import subprocess
import re
import argparse
import sys
import csv

import sys

def print_version_info():
    VERSION = "1.0"
    BUILD_DATE = "2025-12-03"
    AUTHOR = "Louis.Hsieh"
    TOOL_NAME = "PCIe Diagnostic Tool"

    print("=" * 60)
    print(f"{TOOL_NAME}")
    print("-" * 60)
    print(f"Version      : {VERSION}")
    print(f"Build Date   : {BUILD_DATE}")
    print(f"Author       : {AUTHOR}")
    #print(f"Python       : {sys.version.split()[0]}")
    #print(f"Platform     : {sys.platform}")
    print("=" * 60)
    print("\n")


# -----------------------------------------------------------------------------
# get_lspci_blocks
# -----------------------------------------------------------------------------
def get_lspci_blocks():
    out = subprocess.check_output(["lspci", "-Dvvvnn"], text=True)
    lines = out.splitlines()

    devices = []
    current = []

    for line in lines:
        if line and not line.startswith("\t"):
            if current:
                devices.append(current)
            current = [line]
        else:
            current.append(line)

    if current:
        devices.append(current)

    return devices

# -----------------------------------------------------------------------------
# parse_domain_bus_dev_func
# -----------------------------------------------------------------------------
def parse_domain_bus_dev_func(header_line):
    """
    """
    m = re.match(
        r"^([0-9a-fA-F]{4}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])\s+(.*)$",
        header_line
    )
    if not m:
        #return None, None, None, None, header_line0 -> return None not safe
        return "????", "??", "??", "?", header_line
    return m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)

# -----------------------------------------------------------------------------
# parse_vendor_device
# -----------------------------------------------------------------------------
def parse_vendor_device(rest):
    m = re.search(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", rest)
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2).lower()

# -----------------------------------------------------------------------------
# parse_bus_dev_func
# -----------------------------------------------------------------------------
def parse_bus_dev_func(header_line):
    m = re.match(r"^([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])\s+(.*)$", header_line)
    if not m:
        return None, None, None, header_line
    return m.group(1), m.group(2), m.group(3), m.group(4)

# -----------------------------------------------------------------------------
# Helpers: PN (Port Number) & Rev (Revision)
# -----------------------------------------------------------------------------
def get_port_number(block):
    """
    Parse 'LnkCap: Port #<n>' → return 'NN' (zero-filled 2 digits).
    Fallback '00' if not found.
    """
    for line in block:
        line = line.strip()
        if line.startswith("LnkCap:"):
            m = re.search(r"Port\s+#(\d+)", line)
            if m:
                return m.group(1).zfill(2)
    return "00"

def get_revision_from_header(header_line):
    """
    Parse '(rev XX)' at end of header line → return 'xx' (lowercase hex).
    Empty string if not found.
    """
    m = re.search(r"\(rev\s+([0-9a-fA-F]{2})\)", header_line, re.I)
    return m.group(1).lower() if m else ""

# -----------------------------------------------------------------------------
# get_link_info
# -----------------------------------------------------------------------------
def get_link_info(block):
    max_width = "0X"
    cur_width = "0X"
    max_speed = "0.0"
    cur_speed = "0.0"
    tar_speed = "0.0"

    for line in block:
        line = line.strip()

        if line.startswith("LnkCap:"):
            m_w = re.search(r"Width x(\d+)", line)
            if m_w:
                max_width = f"{m_w.group(1)}X"
            m_s = re.search(r"Speed (\d+(\.\d+)?)GT/s", line)
            if m_s:
                max_speed = m_s.group(1)

        elif line.startswith("LnkSta:"):
            m_w = re.search(r"Width x(\d+)", line)
            if m_w:
                cur_width = f"{m_w.group(1)}X"
            m_s = re.search(r"Speed (\d+(\.\d+)?)GT/s", line)
            if m_s:
                cur_speed = m_s.group(1)

        elif line.startswith("LnkCtl2:"):
            m_s = re.search(r"Target Link Speed:\s+(\d+(\.\d+)?)GT/s", line)
            if m_s:
                tar_speed = m_s.group(1)

    if tar_speed == "0.0":
        tar_speed = cur_speed

    return max_width, cur_width, max_speed, cur_speed, tar_speed

# -----------------------------------------------------------------------------
# get_type_from_header
# -----------------------------------------------------------------------------
def get_type_from_header(rest):
    rest_low = rest.lower()
    if "pci bridge" in rest_low:
        return "PCI/PCI Bridge"
    if "usb controller" in rest_low:
        return "USB 3.0"
    if "sata controller" in rest_low:
        return "SATA controller"
    if "ethernet controller" in rest_low:
        return "Ethernet controller"
    return rest.split(":")[0]

# -----------------------------------------------------------------------------
# build_actual_list
# -----------------------------------------------------------------------------
def build_actual_list():
    devices = get_lspci_blocks()
    rows = []

    for dev_block in devices:
        header = dev_block[0]
        #bus, dev_num, func, rest = parse_bus_dev_func(header)
        dom, bus, dev_num, func, rest = parse_domain_bus_dev_func(header)
        vendor, device = parse_vendor_device(rest)
        max_w, cur_w, max_s, cur_s, tar_s = get_link_info(dev_block)
        dev_type = get_type_from_header(rest)

        rows.append({
            "dom":dom,
            "bus": bus,
            "dev": dev_num,
            "func": func,
            "vendor": vendor,
            "device": device,
            "max_width": max_w,
            "cur_width": cur_w,
            "max_speed": max_s,
            "cur_speed": cur_s,
            "pn": get_port_number(dev_block),              
            "tar_speed": tar_s,
            "type": dev_type,
            "rev": get_revision_from_header(header),      
        })

    return rows

# -----------------------------------------------------------------------------
# rows_to_dict
# -----------------------------------------------------------------------------
def rows_to_dict(rows):
    d = {}
    for r in rows:
        key = f"{r['dom']}:{r['bus']}:{r['dev']}.{r['func']}"
        d[key] = r
    return d

# -----------------------------------------------------------------------------
# load_config_csv
# -----------------------------------------------------------------------------
def load_config_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "dom":     (row.get("dom")     or "").lower().zfill(4),
                "bus":     (row.get("bus")     or "").lower().zfill(2),
                "dev":     (row.get("dev")     or "").lower().zfill(2),
                "func":    (row.get("func")    or "").lower(),
                "vendor":  (row.get("vendor")  or "").lower(),
                "device":  (row.get("device")  or "").lower(),
                "max_width": row.get("max_width") or "",
                "cur_width": row.get("cur_width") or "",
                "max_speed": row.get("max_speed") or "",
                "cur_speed": row.get("cur_speed") or "",
                "pn":        (row.get("pn") or "").zfill(2) if (row.get("pn") or "").isdigit() else (row.get("pn") or ""),
                "tar_speed": row.get("tar_speed") or "",
                "type":      row.get("type")      or "",
                "rev":      (row.get("rev")      or "").lower(),
            })
    return rows

# -----------------------------------------------------------------------------
# run_mode_show
# -----------------------------------------------------------------------------
def run_mode_show():
    devices = get_lspci_blocks()

    columns = (
        f"{'Dev/Vend':10}" 
        f"{'dom':<6}"
        f"{'Bus':<5}" 
        f"{'Dev':<5}" 
        f"{'Func':<6}" 
        f"{'Max':<5}"
        f"{'Neg':<5}"
        f"{'Sup':<5}"
        f"{'Cur':<5}"
        f"{'PN':<4}"
        f"{'Tar':<5}"
        f"{'Rev':<5}"
        f"{'PCI Device Type'}"
    )
    print(columns)
    print("-" * 79)

    for pcie_dev in devices:
        header = pcie_dev[0]
        #bus, dev, func, rest = parse_bus_dev_func(header)
        dom, bus, dev, func, rest = parse_domain_bus_dev_func(header)
        #if dom == None or bus == None or dev == None or func == None:
        #    return 1
        vendor, device = parse_vendor_device(rest)
        dev_vend = f"{device}{vendor}" if (device and vendor) else "????????"
        max_w, cur_w, max_s, cur_s, tar_s = get_link_info(pcie_dev)

        maxv = max_w
        neg  = cur_w
        sup  = max_s
        cur  = cur_s
        pn   = get_port_number(pcie_dev)           
        tar  = tar_s
        rev  = get_revision_from_header(header)   

        dev_type = get_type_from_header(rest)

        print(
            f"{dev_vend:10}{dom or '??':<6}{bus or '??':<5}{dev or '??':<5}{func or '?':<6}"
            f"{maxv:<5}{neg:<5}{sup:<5}{cur:<5}{pn:<4}{tar:<5}{rev:<5}{dev_type}"
        )

# -----------------------------------------------------------------------------
# run_mode_dump
# -----------------------------------------------------------------------------
def run_mode_dump():
    rows = build_actual_list()
    # CSV header now includes pn, rev
    print("dom,bus,dev,func,vendor,device,max_width,cur_width,max_speed,cur_speed,pn,tar_speed,type,rev")

    for r in rows:
        print("{dom},{bus},{dev},{func},{vendor},{device},{max_width},{cur_width},{max_speed},{cur_speed},{pn},{tar_speed},{type},{rev}".format(
            dom=r["dom"] or "",
            bus=r["bus"] or "",
            dev=r["dev"] or "",
            func=r["func"] or "",
            vendor=r["vendor"] or "",
            device=r["device"] or "",
            max_width=r["max_width"] or "",
            cur_width=r["cur_width"] or "",
            max_speed=r["max_speed"] or "",
            cur_speed=r["cur_speed"] or "",
            pn=r["pn"] or "",
            tar_speed=r["tar_speed"] or "",
            type=r["type"] or "",
            rev=r["rev"] or "",
        ))

# -----------------------------------------------------------------------------
# run_mode_compare
# -----------------------------------------------------------------------------
def run_mode_compare(config_path):
    expected_rows = load_config_csv(config_path)
    expected = rows_to_dict(expected_rows)

    actual_rows = build_actual_list()
    actual = rows_to_dict(actual_rows)

    fields = [
        "vendor",
        "device",
        "max_width",
        "cur_width",
        "max_speed",
        "cur_speed",
        "pn",         
        "tar_speed",
        "type",
        "rev",       
    ]

    diffs = []

    for key, exp in expected.items():
        if key not in actual:
            diffs.append({
                "type": "MISSING",
                "location": key,
                "expected": exp,
            })
            continue

        act = actual[key]

        for f in fields:
            ev_raw = exp.get(f)
            ev = str(ev_raw or "").strip()

            av_raw = act.get(f)
            av = str(av_raw or "").strip()

            if not ev:
                continue
            if ev != av:
                diffs.append({
                    "type": "MISMATCH",
                    "location": key,
                    "expected": exp,
                    "field": f,
                    "expected_val": ev,
                    "actual": av,
                })
    print_version_info()
    if not diffs:
        print("[INFO] compare result: PASS")
        return 0

    print("[INFO] compare result: FAIL")

    columns = (
        f"{'Dev/Vend':10}" 
        f"{'dom':<6}"
        f"{'Bus':<5}" 
        f"{'Dev':<5}" 
        f"{'Func':<6}" 
        f"{'Max':<5}"
        f"{'Neg':<5}"
        f"{'Sup':<5}"
        f"{'Cur':<5}"
        f"{'PN':<4}"
        f"{'Tar':<5}"
        f"{'Rev':<5}"
        f"{'PCI Device Type'}"
    )
    print(columns)
    print("-" * 82)

    # tarverse diffs list
    for d in diffs:
        error_type = d["type"]

        # show error
        exp = d["expected"]
        dom = exp["dom"]
        bus = exp["bus"]
        dev = exp["dev"]
        func = exp["func"]
        vendor = exp["vendor"]
        device = exp["device"]
        maxv = exp["max_width"]
        neg = exp["cur_width"]
        sup = exp["max_speed"]
        cur = exp["cur_speed"]
        tar = exp["tar_speed"]
        pn  = exp["pn"]
        rev = exp["rev"]
        dev_type = exp["type"]
        dev_vend = f"{vendor or '????'}{device or '????'}"

        if error_type == "MISSING":
            key = d["location"]
            error_msg = " => addr: " + key + " not in system"
        elif error_type == "MISMATCH":
            error_msg = " => field: [" + d["field"] + "] is mismatch, expected value: [" + d["expected_val"] + "], actual value: [" + d["actual"] + "]"


        red = "\033[31m"
        blue = "\033[34m"
        reset = "\033[0m"

        print(f"{red}{dev_vend:10}{dom or '??':<6}{bus or '??':<5}{dev or '??':<5}{func or '?':<6}"
        f"{maxv:<5}{neg:<5}{sup:<5}{cur:<5}{pn:<4}{tar:<5}{rev:<5}{dev_type}{reset}"
        f"{blue}{error_msg}{reset}"
        )

    if (len(diffs)>0): return 1

# -----------------------------------------------------------------------------
# main / argparse
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="PCIe helper tool: show current lspci info, dump as csv, or compare with a config.",
    )
    parser.add_argument(
        "--mode",
        choices=["show", "dump", "compare"],
        default="show",
    )
    parser.add_argument(
        "--config",
        help="config file to compare, required when --mode=compare",
    )
    args = parser.parse_args()

    if args.mode == "show":
        run_mode_show()
        sys.exit(0)
    elif args.mode == "dump":
        run_mode_dump()
        sys.exit(0)
    elif args.mode == "compare":
        if not args.config:
            print("[ERROR] --config is required when --mode=compare", file=sys.stderr)
            sys.exit(1)
        rc = run_mode_compare(args.config)
        sys.exit(rc)

if __name__ == "__main__":
    main()

