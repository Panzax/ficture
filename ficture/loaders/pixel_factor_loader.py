import sys, os, gzip, copy, re, logging, warnings
import numpy as np
import pandas as pd
import subprocess as sp


class BlockIndexedLoader:

    def __init__(
        self,
        input,
        xmin=-np.inf,
        xmax=np.inf,
        ymin=-np.inf,
        ymax=np.inf,
        full=False,
        offseted=True,
        filter_cmd="",
        idtype={},
        chunksize=1000000,
    ) -> None:
        self.meta = {}
        self.header = []
        nheader = 0
        with gzip.open(input, "rt") as rf:
            for line in rf:
                if line[0] != "#":
                    break
                nheader += 1
                if line[:2] == "##":
                    wd = line[(line.rfind("#") + 1) :].strip().split(";")
                    wd = [[y.strip() for y in x.strip().split("=")] for x in wd]
                    for v in wd:
                        if v[1].lstrip("-+").isdigit():
                            self.meta[v[0]] = int(v[1])
                        elif v[1].replace(".", "", 1).lstrip("-+").isdigit():
                            self.meta[v[0]] = float(v[1])
                        else:
                            self.meta[v[0]] = v[1]
                else:
                    self.header = line[(line.rfind("#") + 1) :].strip().split("\t")
        logging.basicConfig(
            level=getattr(logging, "INFO", None),
            format="%(asctime)s %(message)s",
            datefmt="%I:%M:%S %p",
        )
        logging.info("Read header %s", self.meta)
        xmin = float(xmin)
        xmax = float(xmax)
        ymin = float(ymin)
        ymax = float(ymax)

        # Handle empty offset values
        self.meta["OFFSET_X"] = (
            float(self.meta["OFFSET_X"]) if self.meta["OFFSET_X"] else 0.0
        )
        self.meta["OFFSET_Y"] = (
            float(self.meta["OFFSET_Y"]) if self.meta["OFFSET_Y"] else 0.0
        )
        self.meta["SCALE"] = float(self.meta["SCALE"])
        print(self.meta["SIZE_X"], self.meta["SIZE_Y"], self.meta["SCALE"])
        self.meta["SIZE_X"] = (
            float(self.meta["SIZE_X"]) if self.meta["SIZE_X"] else xmax - xmin + 1
        )
        self.meta["SIZE_Y"] = (
            float(self.meta["SIZE_Y"]) if self.meta["SIZE_Y"] else ymax - ymin + 1
        )

        if np.isinf(xmin) and np.isinf(xmax) and np.isinf(ymin) and np.isinf(ymax):
            full = True
        self.xmin = xmin if offseted else xmin - self.meta["OFFSET_X"]
        self.xmax = xmax if offseted else xmax - self.meta["OFFSET_X"]
        self.ymin = ymin if offseted else ymin - self.meta["OFFSET_Y"]
        self.ymax = ymax if offseted else ymax - self.meta["OFFSET_Y"]
        # Input reader
        dty = {"BLOCK": str, "X": int, "Y": int}
        if "TOPK" in self.meta:
            dty.update({f"K{k+1}": str for k in range(self.meta["TOPK"])})
            dty.update({f"P{k+1}": float for k in range(self.meta["TOPK"])})
        if len(idtype) > 0:
            dty.update(idtype)
        self.file_is_open = True
        self.xmin = max(xmin, 0)
        self.xmax = min(xmax, self.meta["SIZE_X"])
        self.ymin = max(ymin, 0)
        self.ymax = min(ymax, self.meta["SIZE_Y"])
        if full:
            self.reader = pd.read_csv(
                input,
                sep="\t",
                skiprows=nheader,
                chunksize=chunksize,
                names=self.header,
                dtype=dty,
            )

            # filepath = input

            # # First, let's look at the raw content
            # print("Raw file content (first 10 lines):")
            # with gzip.open(filepath, 'rt') as f:
            #     for i, line in enumerate(f):
            #         print(line.strip())
            #         if i >= 20:
            #             break

            # print("\nTrying to read with pandas:")
            # # Try reading without skipping rows
            # df = pd.read_csv(filepath, sep='\t', compression='gzip')
            # print(f"\nShape with no skipping: {df.shape}")

            # # Check the number of header rows
            # with gzip.open(filepath, 'rt') as f:
            #     header_count = 0
            #     for line in f:
            #         if line.startswith('#'):
            #             header_count += 1
            #         else:
            #             break
            # print(f"\nNumber of header rows: {header_count}")

            ## Try reading with explicit header handling
            # df = pd.read_csv(filepath, 
            #                 sep='\t', 
            #                 compression='gzip',
            #                 skiprows=header_count,
            #                 names=['BLOCK', 'X', 'Y', 'K1', 'K2', 'K3', 'P1', 'P2', 'P3'])
            # print(f"\nShape with header skipping: {df.shape}")
            # print("\nFirst few rows:")
            # print(df.head())

        else:
            # Translate target region to index
            if self.meta["BLOCK_AXIS"] == "Y":
                block = [
                    int(x / self.meta["BLOCK_SIZE"]) for x in [self.ymin, self.ymax - 1]
                ]
                pos_range = [
                    int(x * self.meta["SCALE"]) for x in [self.xmin, self.xmax]
                ]
            else:
                block = [
                    int(x / self.meta["BLOCK_SIZE"]) for x in [self.xmin, self.xmax - 1]
                ]
                pos_range = [
                    int(x * self.meta["SCALE"]) for x in [self.ymin, self.ymax]
                ]
            block = np.arange(block[0], block[1] + 1) * self.meta["BLOCK_SIZE"]
            query = []
            pos_range = "-".join([str(x) for x in pos_range])
            for i, b in enumerate(block):
                query.append(str(b) + ":" + pos_range)

            cmd = " ".join(["tabix", input] + query)
            if filter_cmd != "":
                cmd = cmd + " | " + filter_cmd
            logging.info(cmd)
            process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.STDOUT, shell=True)
            self.reader = pd.read_csv(
                process.stdout,
                sep="\t",
                chunksize=chunksize,
                names=self.header,
                dtype=dty,
            )

    def __iter__(self):
        return self

    def __next__(self):
        if not self.file_is_open:
            raise StopIteration
        try:
            chunk = next(self.reader)
        except StopIteration:
            self.file_is_open = False
            raise StopIteration
        chunk["X"] = chunk.X / self.meta["SCALE"]
        chunk["Y"] = chunk.Y / self.meta["SCALE"]
        drop_index = chunk.index[
            (chunk.X < self.xmin)
            | (chunk.X > self.xmax)
            | (chunk.Y < self.ymin)
            | (chunk.Y > self.ymax)
        ]
        return chunk.drop(index=drop_index)
