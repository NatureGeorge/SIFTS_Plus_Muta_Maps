# @Created Date: 2020-01-12 01:27:18 pm
# @Filename: decode.py
# @Email:  1730416009@stu.suda.edu.cn
# @Author: ZeFeng Zhu
# @Last Modified: 2020-02-11 04:22:22 pm
# @Copyright (c) 2020 MinghuiGroup, Soochow University
import os
import numpy as np
import pandas as pd
import pyexcel as pe
import tablib
from tablib import InvalidDimensions, UnsupportedFormat
from typing import Union, Optional, Iterator, Iterable, Set, Dict, List, Any, Generator, Callable, Tuple
from json import JSONDecodeError
import ujson as json
import time
from pathlib import Path
from logging import Logger
from collections import OrderedDict, defaultdict
from unsync import unsync, Unfuture
from Bio import Align, SeqIO
from Bio.SubsMat import MatrixInfo as matlist
from functools import lru_cache
from Muta3DMaps.core.utils import decompression, related_dataframe
from Muta3DMaps.core.log import Abclog
from Muta3DMaps.core.retrieve.fetchFiles import UnsyncFetch

API_LYST: List = sorted(['summary', 'molecules', 'experiment', 'ligand_monomers',
                   'modified_AA_or_NA', 'mutated_AA_or_NA', 'status',
                   'polymer_coverage', 'secondary_structure',
                   'residue_listing', 'binding_sites', 'files', 'observed_residues_ratio',
                   'assembly', 'electron_density_statistics',
                   'cofactor', 'drugbank', 'related_experiment_data'])

BASE_URL: str = 'https://www.ebi.ac.uk/pdbe/api/'

FTP_URL: str = 'ftp://ftp.ebi.ac.uk/'

FTP_DEFAULT_PATH: str = 'pub/databases/msd/sifts/flatfiles/tsv/uniprot_pdb.tsv.gz'

FUNCS = list()

def dispatch_on_set(keys: Set):
    '''
    Decorator to add new dispatch functions
    '''
    def register(func):
        FUNCS.append((func, set(keys)))
        return func
    return register


def traversePDBeData(query: Any, *args):
    for func, keySet in FUNCS:
        if query in keySet:
            return func(*args)
    else:
        raise ValueError(f'Invalid query: {query}')


def convertJson2other(
        data: Union[List, str, None], 
        append_data: Union[Iterable, Iterator],
        converter: Optional[tablib.Dataset] = None, 
        export_format: str = 'tsv', 
        ignore_headers: Union[bool, int] = False, 
        log_func=print) -> Any:
    '''
    Convert valid json-string/dict into specified format via `tablib.Dataset.export`
    '''
    if converter is None:
        converter = tablib.Dataset()
    try:
        if isinstance(data, str):
            converter.json = data
        elif isinstance(data, List):
            converter.dict = data
        elif data is None:
            pass
        else:
            log_func(f'Invalid type for data`: {type(data)}')
            return None
        for data_to_append in append_data:
            converter.append_col(*data_to_append)
        if ignore_headers:
            converter.headers = None
        return converter.export(export_format)
    except KeyError:
        log_func('Not a valid json-string/dict to convert format via `tablib.Dataset.export`')
    except JSONDecodeError:
        log_func(f'Invalid json string')
    except InvalidDimensions:
        log_func('Invalid data or append_data')
    except UnsupportedFormat:
        log_func(f'Invalid export_format: {export_format}')


class SeqRangeReader(object):
    def __init__(self, name_group):
        self.name = name_group  # ('pdb_id', 'chain_id', 'UniProt')
        self.pdb_range = []
        self.unp_range = []

    def output(self):
        if self.pdb_range:
            pdb_range = json.dumps(self.pdb_range)
            unp_range = json.dumps(self.unp_range)
            return pdb_range, unp_range
        else:
            return self.default_pdb_range, self.default_unp_range

    def check(self, name_group_to_check, data_group):
        self.default_pdb_range = '[[%s, %s]]' % data_group[:2]
        self.default_unp_range = '[[%s, %s]]' % data_group[2:4]

        if self.name == name_group_to_check:
            self.pdb_range.append([int(data_group[0]), int(data_group[1])])
            self.unp_range.append([int(data_group[2]), int(data_group[3])])
        else:
            self.name = name_group_to_check
            self.pdb_range = [[int(data_group[0]), int(data_group[1])]]
            self.unp_range = [[int(data_group[2]), int(data_group[3])]]

        return self.output()


class SeqPairwiseAlign(object):
    def __init__(self):
        self.seqa = None
        self.seqb = None
        self.aligner = Align.PairwiseAligner()
        self.aligner.mode = 'global'
        self.aligner.open_gap_score = -10
        self.aligner.extend_gap_score = -0.5
        self.aligner.substitution_matrix = matlist.blosum62
        self.alignment_count = 0

    @lru_cache()
    def makeAlignment(self, seqa, seqb):
        if seqa is None or seqb is None:
            return np.nan, np.nan
        self.seqa = seqa
        self.seqb = seqb
        alignments = self.aligner.align(seqa, seqb)
        for alignment in alignments:
            result = self.getAlignmentSegment(alignment)
            self.alignment_count += 1
            return json.dumps(result[0]), json.dumps(result[1])

    @staticmethod
    def getAlignmentSegment(alignment):
        segments1 = []
        segments2 = []
        i1, i2 = alignment.path[0]
        for node in alignment.path[1:]:
            j1, j2 = node
            if j1 > i1 and j2 > i2:
                segment1 = [i1 + 1, j1]
                segment2 = [i2 + 1, j2]
                segments1.append(segment1)
                segments2.append(segment2)
            i1, i2 = j1, j2
        return segments1, segments2


class ProcessPDBe(Abclog):

    converters = {
        'pdb_id': str,
        'chain_id': str,
        'struct_asym_id': str,
        'entity_id': int,
        'author_residue_number': int,
        'residue_number': int,
        'author_insertion_code': str}

    @staticmethod
    def yieldTasks(pdbs: Union[Iterable, Iterator], suffix: str, method: str, folder: str, chunksize: int = 25, task_id: int = 0) -> Generator:
        file_prefix = suffix.replace('/', '%')
        method = method.lower()
        if method == 'post':
            url = f'{BASE_URL}{suffix}'
            for i in range(0, len(pdbs), chunksize):
                params = {'url': url, 'data': ','.join(pdbs[i:i+chunksize])}
                yield method, params, os.path.join(folder, f'{file_prefix}+{task_id}+{i}.json')
        elif method == 'get':
            for pdb in pdbs:
                pdb = pdb.lower()
                yield method, {'url': f'{BASE_URL}{suffix}{pdb}'}, os.path.join(folder, f'{file_prefix}+{pdb}.json')
        else:
            raise ValueError(f'Invalid method: {method}, method should either be "get" or "post"')

    @classmethod
    def retrieve(cls, pdbs: Union[Iterable, Iterator], suffix: str, method: str, folder: str, chunksize: int = 20, concur_req: int = 20, rate: float = 1.5, task_id: int = 0, **kwargs):
        t0 = time.perf_counter()
        res = UnsyncFetch.multi_tasks(
            cls.yieldTasks(pdbs, suffix, method, folder, chunksize, task_id), 
            cls.process, 
            concur_req=concur_req, 
            rate=rate, 
            logger=cls.logger).result()
        elapsed = time.perf_counter() - t0
        cls.logger.info('{} ids downloaded in {:.2f}s'.format(len(res), elapsed))
        return res
    
    @classmethod
    @unsync
    def process(cls, path: Union[str, Path, Unfuture]):
        cls.logger.debug('Start to decode')
        if not isinstance(path, (str, Path)):
            path = path.result()
        if path is None:
            return path
        path = Path(path)
        with path.open() as inFile:
            data = json.load(inFile)
        suffix = path.name.replace('%', '/').split('+')[0]
        new_path = str(path).replace('.json', '.tsv')
        PDBeDecoder.pyexcel_io(
            suffix=suffix,
            data=data,
            filename=new_path,
            delimiter='\t')
        cls.logger.debug(f'Decoded file in {new_path}')
        return new_path


class ProcessSIFTS(ProcessPDBe):
    @classmethod
    def related_UNP_PDB(cls, filePath: Union[str, Path], related_unp: Optional[Iterable] = None, related_pdb: Optional[Iterable] = None):
        '''
        Reference
        
            * http://www.ebi.ac.uk/pdbe/docs/sifts/quick.html
            * A summary of the UniProt to PDB mappings showing the UniProt accession
              followed by a semicolon-separated list of PDB four letter codes.
        '''
        filePath = Path(filePath)
        if filePath.is_dir():
            url = FTP_URL+FTP_DEFAULT_PATH
            task = ('ftp', {'url': url}, str(filePath))
            res = UnsyncFetch.multi_tasks([task]).result()
            filePath = decompression(res[0], remove=False, logger=cls.logger)
        elif filePath.is_file() and filePath.exists():
            filePath = str(filePath)
        else:
            raise ValueError('Invalid value for filePath')

        dfrm = pd.read_csv(filePath, sep='\t', header=1)
        pdb_list = list()
        if related_unp is not None:
            dfrm = dfrm[dfrm['SP_PRIMARY'].isin(related_unp)]
        for i in dfrm.index:
            pdb_list.extend(dfrm.loc[i, 'PDB'].split(';'))
        if related_pdb is not None:
            return set(pdb_list) & set(related_pdb), set(dfrm['SP_PRIMARY'])
        else:
            return set(pdb_list), set(dfrm['SP_PRIMARY'])

    @classmethod
    def reformat(cls, path: str) -> pd.DataFrame:
        dfrm = pd.read_csv(path, sep='\t', converters=cls.converters)
        group_info_col = ['pdb_id', 'chain_id', 'UniProt']
        range_info_col = ['pdb_start', 'pdb_end', 'unp_start', 'unp_end']
        reader = SeqRangeReader(group_info_col)
        dfrm[['sifts_pdb_range', 'sifts_unp_range']] = pd.DataFrame(dfrm.apply(
            lambda x: reader.check(tuple(x[i] for i in group_info_col), tuple(
                x[i] for i in range_info_col)),
            axis=1).values.tolist(), index=dfrm.index)
        dfrm = dfrm.drop(columns=range_info_col).drop_duplicates(
            subset=group_info_col, keep='last').reset_index(drop=True)
        dfrm["Entry"] = dfrm["UniProt"].apply(lambda x: x.split('-')[0])
        return dfrm

    @staticmethod
    def dealWithInDe(dfrm: pd.DataFrame) -> pd.DataFrame:
        def get_gap_list(li: List):
            return [li[i+1][0] - li[i][1] - 1 for i in range(len(li)-1)]

        def get_range_diff(lyst_a: List, lyst_b: List):
            array_a = np.array([ran[1] - ran[0] + 1 for ran in lyst_a])
            array_b = np.array([ran[1] - ran[0] + 1 for ran in lyst_b])
            return (array_a - array_b).tolist()

        def add_tage_to_range(df: pd.DataFrame, tage_name: str):
            # ADD TAGE FOR SIFTS
            df[tage_name] = 'Safe'
            # No Insertion But Deletion[Pure Deletion]
            df.loc[df[(df['group_info'] == 1) & (
                df['sifts_unp_pdb_var'] > 0)].index, tage_name] = 'Deletion'
            # Insertion & No Deletion
            df.loc[df[
                (df['group_info'] != 1) &
                (df['var_0_count'] == df['group_info']) &
                (df['unp_GAP_0_count'] == (df['group_info'] - 1))].index, tage_name] = 'Insertion'
            # Insertion & Deletion
            df.loc[df[
                (df['group_info'] != 1) &
                ((df['var_0_count'] != df['group_info']) |
                 (df['unp_GAP_0_count'] != (df['group_info'] - 1)))].index, tage_name] = 'Insertion & Deletion'

        dfrm['pdb_GAP_list'] = dfrm.apply(lambda x: json.dumps(
            get_gap_list(json.loads(x['sifts_pdb_range']))), axis=1)
        dfrm['unp_GAP_list'] = dfrm.apply(lambda x: json.dumps(
            get_gap_list(json.loads(x['sifts_unp_range']))), axis=1)
        dfrm['var_list'] = dfrm.apply(lambda x: json.dumps(get_range_diff(
            json.loads(x['sifts_unp_range']), json.loads(x['sifts_pdb_range']))), axis=1)
        dfrm['delete'] = dfrm.apply(
            lambda x: '-' in x['var_list'], axis=1)
        dfrm['delete'] = dfrm.apply(
            lambda x: True if '-' in x['unp_GAP_list'] else x['delete'], axis=1)
        dfrm['var_0_count'] = dfrm.apply(
            lambda x: json.loads(x['var_list']).count(0), axis=1)
        dfrm['unp_GAP_0_count'] = dfrm.apply(
            lambda x: json.loads(x['unp_GAP_list']).count(0), axis=1)
        dfrm['group_info'] = dfrm.apply(lambda x: len(
            json.loads(x['sifts_pdb_range'])), axis=1)
        dfrm['sifts_unp_pdb_var'] = dfrm.apply(
            lambda x: json.loads(x['var_list'])[0], axis=1)
        add_tage_to_range(dfrm, tage_name='sifts_range_tage')
        return dfrm

    @staticmethod
    def update_range(dfrm: pd.DataFrame, fasta_col: str, unp_fasta_files_folder: str, new_range_cols=('new_sifts_unp_range', 'new_sifts_pdb_range')) -> pd.DataFrame:
        def getSeq(fasta_path: str):
            unpSeq = None
            try:
                unpSeqOb = SeqIO.read(fasta_path, "fasta")
                unpSeq = unpSeqOb.seq
            except ValueError:
                unpSeqOb = SeqIO.parse(fasta_path, "fasta")
                for record in unpSeqOb:
                    if unp_id in record.id.split('|'):
                        unpSeq = record.seq
            return unpSeq

        focus = ('Deletion', 'Insertion & Deletion')
        focus_index = dfrm[dfrm['sifts_range_tage'].isin(focus)].index
        updated_pdb_range, updated_unp_range = list(), list()
        seqAligner = SeqPairwiseAlign()
        for index in focus_index:
            pdbSeq = dfrm.loc[index, fasta_col]
            unp_entry = dfrm.loc[index, "Entry"]
            unp_id = dfrm.loc[index, "UniProt"]
            try:
                fasta_path = os.path.join(
                    unp_fasta_files_folder, f'{unp_id}.fasta')
                unpSeq = getSeq(fasta_path)
            except FileNotFoundError:
                try:
                    fasta_path = os.path.join(
                        unp_fasta_files_folder, f'{unp_entry}.fasta')
                    unpSeq = getSeq(fasta_path)
                except FileNotFoundError:
                    unpSeq = None
            res = seqAligner.makeAlignment(unpSeq, pdbSeq)
            updated_unp_range.append(res[0])
            updated_pdb_range.append(res[1])

        updated_range_df = pd.DataFrame(
            {new_range_cols[0]: updated_unp_range, new_range_cols[1]: updated_pdb_range}, index=focus_index)
        dfrm = pd.merge(dfrm, updated_range_df, left_index=True,
                        right_index=True, how='left')
        dfrm[new_range_cols[0]] = dfrm.apply(lambda x: x['sifts_unp_range'] if pd.isna(
            x[new_range_cols[0]]) else x[new_range_cols[0]], axis=1)
        dfrm[new_range_cols[1]] = dfrm.apply(lambda x: x['sifts_pdb_range'] if pd.isna(
            x[new_range_cols[1]]) else x[new_range_cols[1]], axis=1)
        return dfrm

    @classmethod
    def main(cls, filePath: Union[str, Path], folder: str, related_unp: Optional[Iterable] = None, related_pdb: Optional[Iterable] = None):
        pdbs, _ = cls.related_UNP_PDB(filePath, related_unp, related_pdb)
        res = cls.retrieve(pdbs, 'mappings/all_isoforms/', 'get', folder)
        # return pd.concat((cls.dealWithInDe(cls.reformat(route)) for route in res if route is not None), sort=False, ignore_index=True)
        return res


class ProcessEntryData(ProcessPDBe):
    @staticmethod
    def related_PDB(pdb_col: str, **kwargs) -> pd.Series:
        dfrm = related_dataframe(**kwargs)
        return dfrm[pdb_col].drop_duplicates()

    @classmethod
    def main(cls, **kwargs):
        pdbs = cls.related_PDB(**kwargs)
        if len(pdbs) > 0:
            res = cls.retrieve(pdbs, **kwargs)
            try:
                return pd.concat((pd.read_csv(route, sep=kwargs.get('sep', '\t'), converters=cls.converters) for route in res if route is not None), sort=False, ignore_index=True)
            except ValueError:
                cls.logger.error('Non-value to concat')
        else:
            return None

    @classmethod
    def unit(cls, pdbs, **kwargs):
        if len(pdbs) > 0:
            res = cls.retrieve(pdbs, **kwargs)
            try:
                return pd.concat((pd.read_csv(route, sep=kwargs.get('sep', '\t'), converters=cls.converters) for route in res if route is not None), sort=False, ignore_index=True)
            except ValueError:
                cls.logger.warning('Non-value to concat')
        else:
            return None

    @staticmethod
    def yieldObserved(dfrm: pd.DataFrame) -> Generator:
        groups = dfrm.groupby(['pdb_id', 'entity_id', 'chain_id'])
        for i, j in groups:
            mod = j.dropna(subset=['chem_comp_id'])
            yield i, len(j[j.observed_ratio.gt(0)]), len(mod[mod.observed_ratio.gt(0)])

    @staticmethod
    def traverse(data: Dict, cols: Tuple, cutoff=50):
        '''
        temp
        '''
        observed_res_count, observed_modified_res_count = cols
        for pdb in data:
            count = 0
            cleaned = 0
            for entity in data[pdb].values():
                for chain in entity.values():
                    if chain[observed_res_count] - chain[observed_modified_res_count] < cutoff:
                        cleaned += 1
                    count += 1
            yield pdb, count, cleaned

    @classmethod
    def pipeline(cls, pdbs: Iterable, folder: str, chunksize: int = 1000):
        for i in range(0, len(pdbs), chunksize):
            related_pdbs = pdbs[i:i+chunksize]
            molecules_dfrm = ProcessEntryData.unit(
                related_pdbs,
                suffix='pdb/entry/molecules/',
                method='post',
                folder=folder,
                task_id=i)
            res_listing_dfrm = ProcessEntryData.unit(
                related_pdbs,
                suffix='pdb/entry/residue_listing/',
                method='get',
                folder=folder,
                task_id=i)
            modified_AA_dfrm = ProcessEntryData.unit(
                related_pdbs,
                suffix='pdb/entry/modified_AA_or_NA/',
                method='post',
                folder=folder,
                task_id=i)
            if modified_AA_dfrm is not None:
                res_listing_dfrm.drop(columns=['author_insertion_code'], inplace=True)
                modified_AA_dfrm.drop(columns=['author_insertion_code'], inplace=True)
                res_listing_mod_dfrm = pd.merge(res_listing_dfrm, modified_AA_dfrm, how='left')
            else:
                res_listing_mod_dfrm = res_listing_dfrm
                res_listing_mod_dfrm['chem_comp_id'] = np.nan
            pro_dfrm = molecules_dfrm[molecules_dfrm.molecule_type.isin(['polypeptide(L)', 'polypeptide(D)'])][['pdb_id', 'entity_id']].reset_index(drop=True)
            pro_res_listing_mod_dfrm = pd.merge(res_listing_mod_dfrm, pro_dfrm)
            data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
            for (pdb_id, entity_id, chain_id), observed_res_count, observed_modified_res_count in cls.yieldObserved(pro_res_listing_mod_dfrm):
                data[pdb_id][entity_id][chain_id]['ob_res'] = observed_res_count
                data[pdb_id][entity_id][chain_id]['ob_moded_res'] = observed_modified_res_count
            with Path(folder, f'clean_pdb_statistic+{i}.tsv').open(mode='w+') as outFile:
                for tup in cls.traverse(data, ('ob_res', 'ob_moded_res')):
                    outFile.write('%s\t%s\t%s\n' % tup)
            with Path(folder, f'clean_pdb_statistic+{i}.json').open(mode='w+') as outFile:
                json.dump(data, outFile)

class PDBeDecoder(object):
    @staticmethod
    def sync_with_pyexcel(*args) -> pe.Sheet:
        records, *remain = args
        sheet = pe.get_sheet(records=records, name_columns_by_row=0)
        if len(remain) > 1:
            append_header, append_value = remain
            append_data = [append_header] + [append_value]*len(records)
            sheet.column += pe.Sheet(append_data)
        return sheet

    @classmethod
    def pyexcel_io(cls, suffix: str, data: Dict, **kwargs) -> pe.Sheet:
        cur_sheet = None
        for res in traversePDBeData(suffix, data):
            try:
                cur_sheet.row += cls.sync_with_pyexcel(*res)
            except AttributeError:
                cur_sheet = cls.sync_with_pyexcel(*res)
        if kwargs:
            cur_sheet.save_as(**kwargs)
        return cur_sheet

    @staticmethod
    def sync_with_tablib(*args) -> tablib.Dataset:
        records, *remain = args
        ob = tablib.Dataset()
        for index in range(len(records)):
            records[index] = OrderedDict(sorted(records[index].items()))
        ob.dict = records
        if len(remain) > 1:
            append_header, append_value = remain
            for i in range(len(append_value)):
                ob.append_col([append_value[i]]*len(records), append_header[i])
        return ob

    @classmethod
    def tablib_io(cls, suffix: str, data: Dict, **kwargs) -> tablib.Dataset:
        cur_ob = None
        for res in traversePDBeData(suffix, data):
            try:
                cur_ob.dict += cls.sync_with_tablib(*res).dict
            except AttributeError:
                cur_ob = cls.sync_with_tablib(*res)
        if kwargs:
            with open(file=kwargs['file'], mode=kwargs.get('mode', 'w+')) as outputFile:
                outputFile.write(cur_ob.export(kwargs['format']))
        return cur_ob

    @staticmethod
    @dispatch_on_set({'pdb/entry/status/', 'pdb/entry/summary/', 'pdb/entry/modified_AA_or_NA/',
                      'pdb/entry/mutated_AA_or_NA/', 'pdb/entry/cofactor/', 'pdb/entry/molecules/',
                      'pdb/entry/ligand_monomers/', 'pdb/entry/experiment/',
                      'pdb/entry/electron_density_statistics/',
                      'pdb/entry/related_experiment_data/', 'pdb/entry/drugbank/'})
    def yieldCommon(data: Dict) -> Generator:
        for pdb in data:
            values = data[pdb]
            for value in values:
                for key in value:
                    if isinstance(value[key], (Dict, List)):
                        value[key] = json.dumps(value[key])
            yield values, ('pdb_id',), (pdb,)

    @staticmethod
    @dispatch_on_set({'pdb/entry/polymer_coverage/'})
    def yieldPolymerCoverage(data: Dict) -> Generator:
        for pdb in data:
            molecules = data[pdb]['molecules']
            for entity in molecules:
                chains = entity['chains']
                for chain in chains:
                    observed = chain['observed']
                    for fragement in observed:
                        for key in ('start', 'end'):
                            fragement[key] = json.dumps(fragement[key])
                    yield observed, ('chain_id', 'struct_asym_id', 'entity_id', 'pdb_id'), (chain['chain_id'], chain['struct_asym_id'], entity['entity_id'], pdb)

    @staticmethod
    @dispatch_on_set({'pdb/entry/observed_residues_ratio/'})
    def yieldObservedResiduesRatio(data: Dict) -> Generator:
        for pdb in data:
            for entity_id, entity in data[pdb].items():
                yield entity, ('entity_id', 'pdb_id'), (entity_id, pdb)

    @staticmethod
    @dispatch_on_set({'pdb/entry/residue_listing/'})
    def yieldResidues(data: Dict) -> Generator:
        for pdb in data:
            molecules = data[pdb]['molecules']
            for entity in molecules:
                chains = entity['chains']
                for chain in chains:
                    residues = chain['residues']
                    for res in residues:
                        if 'multiple_conformers' not in res:
                            res['multiple_conformers'] = None
                        else:
                            res['multiple_conformers'] = json.dumps(res['multiple_conformers'])
                    yield residues, ('chain_id', 'struct_asym_id', 'entity_id', 'pdb_id'), (chain['chain_id'], chain['struct_asym_id'], entity['entity_id'], pdb)

    @staticmethod
    @dispatch_on_set({'pdb/entry/secondary_structure/'})
    def yieldSecondaryStructure(data: Dict) -> Generator:
        for pdb in data:
            molecules = data[pdb]['molecules']
            for entity in molecules:
                chains = entity['chains']
                for chain in chains:
                    secondary_structure = chain['secondary_structure']
                    for name in secondary_structure:
                        fragment = secondary_structure[name]
                        for record in fragment:
                            for key in record:
                                if isinstance(record[key], (Dict, List)):
                                    record[key] = json.dumps(record[key])
                            if 'sheet_id' not in record:
                                record['sheet_id'] = None
                        yield fragment, ('secondary_structure', 'chain_id', 'struct_asym_id', 'entity_id', 'pdb_id'), (name, chain['chain_id'], chain['struct_asym_id'], entity['entity_id'], pdb)

    @staticmethod
    @dispatch_on_set({'pdb/entry/binding_sites/'})
    def yieldBindingSites(data: Dict) -> Generator:
        for pdb in data:
            for site in data[pdb]:
                for tage in ('site_residues', 'ligand_residues'):
                    residues = site[tage]
                    for res in residues:
                        if 'symmetry_symbol' not in res:
                            res['symmetry_symbol'] = None
                    yield residues, ('residues_type', 'details', 'evidence_code', 'site_id', 'pdb_id'), (tage, site['details'], site['evidence_code'], site['site_id'], pdb)

    @staticmethod
    @dispatch_on_set({'pdb/entry/assembly/'})
    def yieldAssembly(data: Dict) -> Generator:
        for pdb in data:
            for biounit in data[pdb]:
                entities = biounit['entities']
                for entity in entities:
                    for key in entity:
                        if isinstance(entity[key], (Dict, List)):
                            entity[key] = json.dumps(entity[key])
                keys = list(biounit)
                keys.remove('entities')
                yield entities, tuple(keys)+('pdb_id',), tuple(biounit[key] for key in keys)+(pdb, )

    @staticmethod
    @dispatch_on_set({'pdb/entry/files/'})
    def yieldAssociatedFiles(data: Dict) -> Generator:
        for pdb in data:
            for key in data[pdb]:
                for innerKey in data[pdb][key]:
                    record = data[pdb][key][innerKey]
                    if record:
                        yield record, ('innerKey', 'key', 'pdb_id'), (innerKey, key, pdb)
                    else:
                        continue

    @staticmethod
    @dispatch_on_set({'mappings/all_isoforms/'})
    def yieldSIFTSRange(data: Dict) -> Generator:
        top_root = next(iter(data))  # PDB_ID or UniProt Isoform ID
        sec_root = next(iter(data[top_root]))  # 'UniProt' or 'PDB'
        child = data[top_root][sec_root]
        thi_root = next(iter(child))
        test_value = child[thi_root]
        # from PDB to UniProt
        if isinstance(test_value, Dict) and sec_root == 'UniProt':
            for uniprot in child:
                name = child[uniprot]['name']
                identifier = child[uniprot]['identifier']
                chains = child[uniprot]['mappings']
                for chain in chains:
                    chain['start'] = json.dumps(chain['start'])
                    chain['end'] = json.dumps(chain['end'])
                    chain['pdb_id'] = top_root
                    chain[sec_root] = uniprot
                    chain['identifier'] = identifier
                    chain['name'] = name
                yield chains, None
        # from UniProt to PDB
        elif isinstance(test_value, List) and sec_root == 'PDB':
            for pdb in child:
                chains = child[pdb]
                for chain in chains:
                    chain['start'] = json.dumps(chain['start'])
                    chain['end'] = json.dumps(chain['end'])
                yield chains, ('pdb_id', 'UniProt'), (pdb, top_root)
        else:
            raise ValueError(f'Unexpected data structure for inputted data: {data}')


# TODO: Chain UniProt ID Mapping -> ProcessSIFTS -> ProcessPDBe
# TODO: Deal with oligomeric PDB
