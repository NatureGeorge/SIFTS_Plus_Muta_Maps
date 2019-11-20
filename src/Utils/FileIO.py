# @Date:   2019-11-20T18:33:41+08:00
# @Email:  1730416009@stu.suda.edu.cn
# @Filename: FileIO.py
# @Last modified time: 2019-11-20T19:32:12+08:00
import os
import gzip
import shutil
import pandas as pd


def decompression(self, path, extension=".gz", remove=True, outputPath=None, logger=None):
    """
    Decompress gz file

    :param str path: The file path of the compressed file
    :param str extension: Compressed file tail, default value: `.gz`
    :param bool remove: Whether remove the compressed file, default value: `True`
    :param str outputPath: File safe path, default value: `None`
    :param logging.Logger logger: logger Object
    """

    """
    with gzip.GzipFile(mode="rb", fileobj=open(path, 'rb')) as raw:
        with open(path[:-len(extension)], "wb") as file:
            file.write(raw.read())
    """
    if outputPath is None:
        outputPath = path[:-len(extension)]

    with gzip.open(path, 'rb') as raw:
        with open(outputPath, 'wb') as file:
            shutil.copyfileobj(raw, file)
    try:
        if remove:
            os.remove(path)
    except Exception as e:
        logger.error(e)


def file_i(path, df, va_tp, sep='\t'):
    try:
        dfrm = pd.read_csv(path, sep=sep, na_values=['', None], keep_default_na=False)
    except Exception:
        dfrm = df
        if not isinstance(dfrm, pd.DataFrame):
            raise Exception('Input: %s=pd.DataFrame() or %s=str' % va_tp)
    return dfrm


def file_o(path, df, mode='a+', header=True):
    if isinstance(path, str):
        df.to_csv(path, sep='\t', index=False, mode=mode, header=header)
