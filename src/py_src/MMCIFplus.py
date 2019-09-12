# @Date:   2019-09-09T16:32:43+08:00
# @Email:  1730416009@stu.suda.edu.cn
# @Filename: MMCIFplus.py
# @Last modified time: 2019-09-12T09:55:33+08:00
import os
import sys
import json
import pandas as pd
import numpy as np
from collections import defaultdict, Iterable, Iterator
import time
import requests
from urllib import request
from retrying import retry
from multiprocessing.dummy import Pool
from Bio.File import as_handle
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Unit import Unit
sys.path.append('./')

MMCIF_FILE_FOLDER = {
    'MMCIF_OLD_FOLDER': [
        '/data1/suntt/process0606/cgc_mmcif_file/',
        '/data1/suntt/CanDriver/Data/PDB_cgc/cgc_mmcif_file/',
        '/data1/suntt/CanDriver/Data/PDB_NEW/mmcif_file/'
        ],
    'MMCIF_NEW_FOLDER': '/home/zzf/Work/SIFTS_Plus_Muta_Maps/data/mmcif_file/',
}

CONFIG = {
    'LIGAND_LIST': [
        'ZN', 'MG', 'CA', 'FE', 'NA', 'MN', 'K', 'NI', 'CU', 'CO', 'CD', 'HG', 'PT', 'MO', 'BE', 'AL', 'BA',
        'RU', 'SR', 'V', 'CS', 'W', 'AU', 'YB', 'LI', 'GD', 'PB', 'Y', 'TL', 'IR', 'RB', 'SM', 'AG',
        'OS', 'PR', 'PD', 'EU', 'RH', 'RE', 'TB', 'TA', 'LU', 'HO', 'CR', 'GA', 'LA', 'SN', 'SB', 'CE',
        'ZR', 'ER', 'TH', 'TI', 'IN', 'HF', 'SC', 'DY', 'BI', 'PA', 'PU', 'AM', 'CM', 'CF', 'GE', 'NB', 'TC',
        'ND', 'PM', 'TM', 'PO', 'FR', 'RA', 'AC', 'NP', 'BK', 'ES', 'FM', 'MD', 'NO', 'LR', 'RF', 'DB', 'SG'],
    'HEADERS': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134'},
    'CHAIN_TYPE_DICT': {
        'polypeptide(L)': 'protein', 'polypeptide(D)': 'protein', 'polydeoxyribonucleotide': 'DNA',
        'polyribonucleotide': 'RNA', 'polydeoxyribonucleotide/polyribonucleotide hybrid': 'DNA+RNA'},
}

DEFAULT_COLS = {
    'COMMON_COL': ['data_', '_pdbx_audit_revision_history.revision_date', '_exptl.method', '_em_3d_reconstruction.resolution', '_refine.ls_d_res_high'],
    'ENTITY_COL': ['_entity.pdbx_mutation', '_entity.id'],
    'TYPE_COL': ['_entity_poly.entity_id', '_entity_poly.pdbx_strand_id', '_entity_poly.type'],
    'SEQRES_COL': ['_pdbx_poly_seq_scheme.pdb_strand_id',
                   '_pdbx_poly_seq_scheme.mon_id', '_pdbx_poly_seq_scheme.pdb_mon_id', '_pdbx_poly_seq_scheme.auth_mon_id',
                   '_pdbx_poly_seq_scheme.ndb_seq_num', '_pdbx_poly_seq_scheme.pdb_seq_num',
                   '_pdbx_poly_seq_scheme.auth_seq_num', '_pdbx_poly_seq_scheme.pdb_ins_code'],
    'LIGAND_COL': [
        '_struct_conn.conn_type_id', '_struct_conn.ptnr1_auth_comp_id', '_struct_conn.ptnr2_auth_comp_id',
        '_struct_conn.ptnr1_auth_asym_id', '_struct_conn.ptnr2_auth_asym_id',
        '_struct_conn.ptnr1_auth_seq_id', '_struct_conn.ptnr2_auth_seq_id'],
    'BIOASS_COL': ['_pdbx_struct_assembly_gen.assembly_id',
                   '_pdbx_struct_assembly_gen.oper_expression',
                   '_pdbx_struct_assembly_gen.asym_id_list',
                   '_pdbx_struct_assembly.oligomeric_count'],
    'METAL_LIGAND_COL': ['metal_ligand_chain_id', 'metal_ligand_content'],
}


class MMCIF2DictPlus(MMCIF2Dict):
    """# Parse a MMCIF file and return a dictionary"""

    def __init__(self, filename, useKeyList):
        """
        <h1>Parse a mmCIF file and return a dictionary</h1>
        <h3>Override ```__init__``` method of ```Bio.PDB.MMCIF2Dict.MMCIF2Dict```</h3>
        <ul>
            <li>```filename```: "Name of the PDB file OR an open filehandle."</li>
            <li>```useKeyList```: "Those MMCIF-keys that user want to collect data from."</li>
        </ul>
        """
        self.quote_chars = ["'", '"']
        self.whitespace_chars = [" ", "\t"]
        with as_handle(filename) as handle:
            loop_flag = False
            key = None
            tokens = self._tokenize(handle)
            try:
                token = next(tokens)
            except StopIteration:
                return  # for Python 3.7 and PEP 479
            self[token[0:5]] = token[5:]
            i = 0
            n = 0
            use = []
            for token in tokens:
                if token.lower() == "loop_":
                    loop_flag = True
                    keys = []
                    i = 0
                    n = 0
                    use = []
                    continue
                elif loop_flag:
                    # The second condition checks we are in the first column
                    # Some mmCIF files (e.g. 4q9r) have values in later columns
                    # starting with an underscore and we don't want to read
                    # these as keys
                    if token.startswith("_") and (n == 0 or i % n == 0):
                        if i > 0:
                            loop_flag = False
                        else:
                            # Additional statement:focus on target data
                            if token in useKeyList:
                                use.append(n)
                                self[token] = []
                            keys.append(token)
                            n += 1
                            continue
                    else:
                        key_index = i % n
                        try:
                            if key_index in use:
                                self[keys[key_index]].append(token)
                        except Exception as e:
                            print(keys, key_index, use)
                            raise Exception(e)
                        i += 1
                        continue
                if key is None:
                    # Additional statement:focus on target data
                    if token in useKeyList:
                        key = token
                else:
                    # Always returns a list
                    self[key] = [token]
                    key = None


class MMCIF2Dfrm(Unit):
    """# Convert MMCIF data into a DataFrame"""

    FUNC_LI_DI = []
    FUNC_LI_DF = []
    pdb_path_li = []

    @property
    def default_use_keys(self):
        use_keys = []
        use_col_li = ['COMMON_COL', 'ENTITY_COL', 'TYPE_COL', 'SEQRES_COL', 'LIGAND_COL', 'BIOASS_COL']
        for col in use_col_li:
            use_keys.extend(DEFAULT_COLS[col])
        return use_keys

    def checkEntityType(sli, cli):
        if isinstance(sli, str):
            sli = json.loads(sli.replace('\'', '"'))
        if isinstance(cli, str):
            cli = json.loads(cli.replace('\'', '"'))
        li = list(zip(sli, cli))
        pli = list(filter(lambda x: 'polypeptide' in x[0], li))
        pli_len = len(pli)
        if pli_len == 1:
            count = pli[0][1].count(',')
            if count == 0:
                return 'mo'
            elif count > 0:
                return 'ho:%d' % (count + 1)
        elif pli_len > 1:
            return 'he:' + ';'.join(i[1] for i in pli)

    def download_cif_file(pdbId, path):
        url = 'https://files.rcsb.org/view/%s.cif' % pdbId
        html = request.urlopen(url).read()
        html = html.decode('utf-8')
        with open(path, 'w') as fw:
            fw.write(html)
            time.sleep(2)

    def get_mmcif_file_path(self, pdbId, download=False):
        print('get_mmcif_file_path(): Working on [%s]' % pdbId)
        new_path = '%s%s.cif' % (MMCIF_FILE_FOLDER['MMCIF_NEW_FOLDER'], pdbId)

        for path in MMCIF_FILE_FOLDER['MMCIF_OLD_FOLDER']:
            old_path = '%s%s.cif' % (path, pdbId)
            if os.path.exists(old_path):
                return old_path

        if os.path.exists(new_path):
            return new_path
        else:
            if download:
                MMCIF2Dfrm.download_cif_file(pdbId, new_path)

            return new_path

    def check_mmcif_file(self, pdb_list):
        def find_unDownloaded_file(pdbId):
            for path in MMCIF_FILE_FOLDER['MMCIF_OLD_FOLDER'] + [MMCIF_FILE_FOLDER['MMCIF_NEW_FOLDER']]:
                old_path = '%s%s.cif' % (path, pdbId)
                if os.path.exists(old_path):
                    MMCIF2Dfrm.pdb_path_li.append(old_path)
                    return False
            return True

        unDownload = list(filter(find_unDownloaded_file, pdb_list))

        @retry(stop_max_attempt_number=3, wait_fixed=1000)
        def download_mmcif_file(pdbId):
            path = '%s%s.cif' % (MMCIF_FILE_FOLDER['MMCIF_NEW_FOLDER'], pdbId)
            print('download_mmcif_file(): %s' % path)
            url = 'https://files.rcsb.org/view/%s.cif' % pdbId
            r = requests.get(url, headers=CONFIG['HEADERS'])
            with open(path, 'wb+') as fw:
                fw.write(r.content)
                time.sleep(2)
                MMCIF2Dfrm.pdb_path_li.append(path)

        pool = Pool(processes=20)
        pool.map(download_mmcif_file, unDownload)

    def get_mmcif_dict(info_key, info_dict, path):
        '''
        <h1>Get MMCIF info in dict-format with the help of ```MMCIF2DictPlus```</h1>
        <b>Creating lists of lists stored in a ```defaultdict``` and prepare for converting it into a ```DataFrame```.</b>
        <h3>Param</h3>
        <ul>
            <li>```info_key```: "Those MMCIF-keys with multiple data which are converted into a list by ```MMCIF2DictPlus```."</li>
            <li>```info_dict```: "The defaultdict that stores data."</li>
            <li>```path```: "The file path of MMCIF-file."</li>
        </ul>
        '''
        assert isinstance(info_key, (Iterable, Iterator)), "Invalid Input, info_key should be iterable"
        assert isinstance(info_dict, defaultdict), "Invalid Input, info_dict should be a defaultdict"

        # info_dict = defaultdict(list)
        mmcif_dict = MMCIF2DictPlus(path, info_key)
        for key in info_key:
            data = mmcif_dict.get(key, np.nan)
            info_dict[key].append(data)

    def dispatch_on_set(keys, func_li):
        """# Decorator to add new dispatch functions."""
        def register(func):
            func_li.append((func, set(keys)))
            return func
        return register

    def handle_mmcif_data(query, data, fun_li):
        use = False
        for func, keySet in fun_li:
            if set(query) >= keySet:
                func(data)
                use = True
        return use

    def get_index(x, y, z): return y[x[z]:x[z + 1]] if len(x) != 1 and z + 1 < len(x) else y[x[z]:]

    @dispatch_on_set(DEFAULT_COLS['SEQRES_COL'], func_li=FUNC_LI_DI)
    def handle_seqres_di(info_dict):
        # Deal with SEQRES_COL
        resides_col_li = DEFAULT_COLS['SEQRES_COL'][1:4]
        mtoTool = Unit.MultiToOne()
        for i in range(len(info_dict[resides_col_li[0]])):
            for resides_col in resides_col_li:
                info_dict[resides_col][i] = ''.join(
                    mtoTool.multi_letter_convert_to_one_letter(j) for j in info_dict[resides_col][i])

        pdbx_poly_key = DEFAULT_COLS['SEQRES_COL'][0]
        for i in range(len(info_dict[pdbx_poly_key])):
            strand_id_index = [0]
            li = info_dict[pdbx_poly_key][i]
            save_id = li[0]
            strand_id_li = [save_id]
            for j in range(len(li)):
                if li[j] != save_id:
                    save_id = li[j]
                    strand_id_index.append(j)
                    strand_id_li.append(save_id)
            info_dict[pdbx_poly_key][i] = strand_id_li

            for col in DEFAULT_COLS['SEQRES_COL'][1:4]:
                info_dict[col][i] = [
                    MMCIF2Dfrm.get_index(strand_id_index, info_dict[col][i], j)
                    for j in range(len(strand_id_index))]

            for col in DEFAULT_COLS['SEQRES_COL'][4:]:
                info_dict[col][i] = [';'.join(
                    MMCIF2Dfrm.get_index(strand_id_index, info_dict[col][i], j))
                    for j in range(len(strand_id_index))]

    @dispatch_on_set(DEFAULT_COLS['LIGAND_COL'], func_li=FUNC_LI_DI)
    def handle_ligand_di(info_dict):
        ligand_col_list = DEFAULT_COLS['LIGAND_COL']
        metal_li = CONFIG['LIGAND_LIST']

        for i in range(len(info_dict[ligand_col_list[0]])):
            temp = pd.isna(info_dict[ligand_col_list[0]][i])
            if temp is True:
                info_dict[DEFAULT_COLS['METAL_LIGAND_COL']
                          [0]].append(np.nan)
                info_dict[DEFAULT_COLS['METAL_LIGAND_COL']
                          [1]].append(np.nan)
                continue
            ligand_col_tp = tuple(info_dict[col][i] for col in ligand_col_list)
            ligand_col_zip_li = list(zip(*ligand_col_tp))

            aa_li = list(MMCIF2Dfrm.SEQ_DICT.keys())[:21]
            metal_ligand_info = list(
                filter(lambda x: x[0] == 'metalc', ligand_col_zip_li))
            # chain_id: _struct_conn.ptnr2_auth_asym_id [4]
            sub_metal_ligand_info_1 = filter(
                lambda x: x[1] in metal_li and x[2] in aa_li, metal_ligand_info)
            # chain_id: _struct_conn.ptnr1_auth_asym_id [3]
            sub_metal_ligand_info_2 = filter(
                lambda x: x[2] in metal_li and x[1] in aa_li, metal_ligand_info)

            new_metal_ligand_info = []
            for tp in sub_metal_ligand_info_1:
                new_metal_ligand_info.append(
                    (tp[4], tp[1], tp[5], tp[2], tp[6]))
            for tp in sub_metal_ligand_info_2:
                new_metal_ligand_info.append(
                    (tp[3], tp[2], tp[6], tp[1], tp[5]))

            new_metal_ligand_info.sort(key=lambda x: x[0])
            try:
                save_id = new_metal_ligand_info[0][0]
                # print(new_metal_ligand_info)
            except IndexError:
                info_dict[DEFAULT_COLS['METAL_LIGAND_COL']
                          [0]].append(np.nan)
                info_dict[DEFAULT_COLS['METAL_LIGAND_COL']
                          [1]].append(np.nan)
                continue

            strand_id_li = [save_id]
            strand_id_index = [0]
            for j in range(len(new_metal_ligand_info)):
                if new_metal_ligand_info[j][0] != save_id:
                    save_id = new_metal_ligand_info[j][0]
                    strand_id_index.append(j)
                    strand_id_li.append(save_id)

            info_dict[DEFAULT_COLS['METAL_LIGAND_COL'][0]].append(strand_id_li)
            info_dict[DEFAULT_COLS['METAL_LIGAND_COL'][1]].append(
                [MMCIF2Dfrm.get_index(strand_id_index, [ele[1:] for ele in new_metal_ligand_info], j) for j in range(len(strand_id_index))]
            )

    @dispatch_on_set(DEFAULT_COLS['COMMON_COL'], func_li=FUNC_LI_DF)
    def handle_common_df(df):
        # Deal with the date of structure
        df['initial_version_time'] = df.apply(
            lambda x: x[DEFAULT_COLS['COMMON_COL'][1]][0], axis=1)
        df['newest_version_time'] = df.apply(
            lambda x: x[DEFAULT_COLS['COMMON_COL'][1]][-1], axis=1)
        # Deal with the resolution
        df['resolution'] = df.apply(lambda x: x[DEFAULT_COLS['COMMON_COL'][4]], axis=1)
        df['resolution'] = df.apply(lambda x: x[DEFAULT_COLS['COMMON_COL'][3]] if isinstance(x['resolution'], float) else x['resolution'], axis=1)

    @dispatch_on_set(DEFAULT_COLS['ENTITY_COL'], func_li=FUNC_LI_DF)
    def handle_entity_df(df):
        # Deal with the mutations
        def muta_count(x): return x.count(',') + 1 if x != '?' else 0
        df['mutation_num'] = df.apply(lambda x: [muta_count(i) for i in x['_entity.pdbx_mutation']], axis=1)

    @dispatch_on_set(DEFAULT_COLS['TYPE_COL'], func_li=FUNC_LI_DF)
    def handle_type_df(df):
        # Deal with chain type
        def get_chainType_fun(ele): return CONFIG['CHAIN_TYPE_DICT'].get(ele, 'other')
        df['pdb_contain_chain_type'] = df.apply(lambda x: ','.join(sorted(set(map(get_chainType_fun, json.loads(x['_entity_poly.type'].replace('\'', '"'))))))
                                                if isinstance(x['_entity_poly.type'], str)
                                                else ','.join(sorted(set(map(get_chainType_fun, x['_entity_poly.type'])))), axis=1)
        # Add Info about pdb_type
        df['pdb_type_MMCIF'] = df.apply(lambda x: MMCIF2Dfrm.checkEntityType(
            x['_entity_poly.type'], x['_entity_poly.pdbx_strand_id']), axis=1)

    @dispatch_on_set(['_pdbx_poly_seq_scheme.mon_id', '_entity_poly.type'], func_li=FUNC_LI_DF)
    def handle_unk_df(df):
        # Deal with UNK_ALL in chain
        def get_unk_fun(ele): return len(ele) == ele.count('!')
        df['UNK_ALL_IN_CHAIN'] = df.apply(lambda x: list(map(get_unk_fun, json.loads(x['_pdbx_poly_seq_scheme.mon_id'].replace('\'', '"'))))
                                          if isinstance(x['_entity_poly.type'], str)
                                          else list(map(get_unk_fun, x['_pdbx_poly_seq_scheme.mon_id'])), axis=1)
        # Deal with UNK_ALL in chains of a pdb
        df['contains_unk_in_chain_pdb'] = df.apply(
            lambda x: len(set(x['UNK_ALL_IN_CHAIN'])) == 2, axis=1)

    @dispatch_on_set(DEFAULT_COLS['BIOASS_COL']+['_pdbx_poly_seq_scheme.pdb_strand_id'], func_li=FUNC_LI_DF)
    def handle_bioas_df(df):
        '''
        ### Deal with Biological Assemblies in PDB</h3>
        #### Example
        Key|Value
        -|-
        pdb_id|3A6P
        _entity.id|[1, 2, 3, 4, 5, 6, 7]
        _entity_poly.entity_id|[1, 2, 3, 4, 5]
        _entity_poly.pdbx_strand_id|[A,F, B,G, C,H, D,I, E,J]
        _entity_poly.type|[polypeptide(L), polypeptide(L), polypeptide(L)...
        _pdbx_struct_assembly_gen.assembly_id|[1, 2]
        _pdbx_struct_assembly_gen.oper_expression|[1, 1]
        _pdbx_struct_assembly_gen.asym_id_list|[A,B,C,D,E,K,L, F,G,H,I,J,M,N]
        _pdbx_struct_assembly.oligomeric_count|[5, 5]
        ---
        ```_pdbx_struct_assembly_gen.asym_id_list``` -> [A,B,C,D,E,~~K,L,~~ F,G,H,I,J,~~M,N~~]
        ```_pdbx_poly_seq_scheme.pdb_strand_id```
        > For more examples, please goto [here](https://naturegeorge.github.io/BioinforResearch/md_for_MMCIF2Dfrm.html "Link")
        '''
        def getBioUnitInfo(au_id_li, au_asym_id_li, oli, pl_asym_id_li):
            au_dict = defaultdict(list)
            for index in range(len(au_id_li)):
                au_dict[au_id_li[index]].extend([chain for chain in au_asym_id_li[index].split(',') if chain in pl_asym_id_li])
            for index, key in enumerate(sorted(au_dict.keys())):
                au_dict[key] = (int(oli[index]), au_dict[key])
            return json.dumps(au_dict)

        df['bioUnit'] = df.apply(lambda x: getBioUnitInfo(
                x['_pdbx_struct_assembly_gen.assembly_id'],
                x['_pdbx_struct_assembly_gen.asym_id_list'],
                x['_pdbx_struct_assembly.oligomeric_count'],
                x['_pdbx_poly_seq_scheme.pdb_strand_id']) if not isinstance(x['_pdbx_struct_assembly_gen.assembly_id'], float) else np.nan, axis=1)

    def mmcif_dict2dfrm(self, path_list, useKeyList=False, outputPath=False):
        '''
        <h1>Convert MMCIF data into a DataFrame</h1>
        <b>Creating a DataFrame stores all the target data of related MMCIF file in ```path_list```.</b>
        <h3>Param</h3>
        <ul>
            <li>```path_list```: "The list of MMCIF file path OR open filehandle"</li>
            <li>```useKeyList```: "The MMCIF-keys that you want to collect data from."</li>
            <li>```outputPath```: "The savepath of the final DataFrame. Default value:```False```"</li>
        </ul>
        <h3>Return</h3>
        <ul><li>```pandas.DataFrame```</li></ul>
        '''
        info_dict = defaultdict(list)
        for path in path_list:
            if path[-3:] != 'cif':
                print('Not a valid MMCIF file path: %s' % path)
            else:
                if not useKeyList:
                    useKeyList = self.default_use_keys
                MMCIF2Dfrm.get_mmcif_dict(useKeyList, info_dict, path)
        # Modify the dict
        modified_di = MMCIF2Dfrm.handle_mmcif_data(useKeyList, info_dict, MMCIF2Dfrm.FUNC_LI_DI)
        if modified_di:
            print('handle_mmcif_data(): Modified Dict')
        # Transform dict into dfrm
        df = pd.DataFrame(info_dict)
        # Modify the dfrm
        modified_df = MMCIF2Dfrm.handle_mmcif_data(useKeyList, df, MMCIF2Dfrm.FUNC_LI_DF)
        if modified_df:
            print('handle_mmcif_data(): Modified Dfrm')
        # Change the columns
        df.rename(
            columns={DEFAULT_COLS['COMMON_COL'][0]: 'pdb_id', DEFAULT_COLS['COMMON_COL'][2]: 'method'}, inplace=True)

        if os.path.exists(outputPath):
            self.file_o(outputPath, df, mode='a+', header=False)
        else:
            self.file_o(outputPath, df)
        return df

    def handle_mmcif_dfrm(self, dfrm, outputPath=False):

        def get_sub_df(df, i, spe_col_li, common_col_li):
            try:
                a = pd.DataFrame({key: df.loc[i, key] for key in spe_col_li})
            except Exception:
                try:
                    a = pd.DataFrame({key: json.loads(df.loc[i, key].replace('\'', '"').replace('False', 'false').replace('True', 'true')) for key in spe_col_li})
                except Exception:
                    a = pd.DataFrame({key: [df.loc[i, key]] for key in spe_col_li})

            for common_col in common_col_li:
                da = df.loc[i, common_col]
                if isinstance(da, list):
                    a[common_col] = ','.join(df.loc[i, common_col])
                elif isinstance(da, (str, bool, np.bool_)) or pd.isna(da):
                    a[common_col] = da
                else:
                    print('get_sub_df(): WARNING: %s -> %s(%s)' % (common_col, da, type(da)))
                    a[common_col] = da
            return a

        def sub_handle_df(df, spe_col_li, common_col_li):
            df_li = []
            for i in df.index:
                df_li.append(get_sub_df(df, i, spe_col_li, common_col_li))
            return pd.concat(df_li, ignore_index=True)

        entity_poly_df = sub_handle_df(
            dfrm, DEFAULT_COLS['ENTITY_COL'] + ['mutation_num'], ['pdb_id'])
        type_poly_df = sub_handle_df(
            dfrm, DEFAULT_COLS['TYPE_COL'], ['pdb_id'])
        basic_df = sub_handle_df(dfrm, DEFAULT_COLS['SEQRES_COL'] + ['UNK_ALL_IN_CHAIN'],
            [
                'pdb_id', 'method', 'initial_version_time',
                'newest_version_time', 'resolution', 'pdb_contain_chain_type',
                'contains_unk_in_chain_pdb', 'pdb_type_MMCIF', 'bioUnit'
            ]
            + DEFAULT_COLS['COMMON_COL'][3:5]
            + DEFAULT_COLS['BIOASS_COL'])
        ligand_df = sub_handle_df(
            dfrm, DEFAULT_COLS['METAL_LIGAND_COL'], ['pdb_id'])

        new_type_poly_df = type_poly_df.drop(DEFAULT_COLS['TYPE_COL'][1], axis=1).join(
            type_poly_df[DEFAULT_COLS['TYPE_COL'][1]].str.split(',', expand=True).stack().reset_index(level=1, drop=True).rename('chain_id'))

        entity_poly_df.rename(columns={
                              '_entity.pdbx_mutation': 'mutation_content', '_entity.id': 'entity_id'}, inplace=True)
        new_type_poly_df.rename(columns={
                                '_entity_poly.entity_id': 'entity_id', '_entity_poly.type': 'protein_type'}, inplace=True)
        basic_df.rename(
            columns={'_pdbx_poly_seq_scheme.pdb_strand_id': 'chain_id'}, inplace=True)
        ligand_df.rename(
            columns={DEFAULT_COLS['METAL_LIGAND_COL'][0]: 'chain_id'}, inplace=True)

        if ligand_df['chain_id'].isnull().sum() == len(ligand_df):
            basic_df[DEFAULT_COLS['METAL_LIGAND_COL'][1]] = np.nan
            df_1 = basic_df
        else:
            df_1 = pd.merge(basic_df, ligand_df, how='left')
        df_2 = pd.merge(new_type_poly_df, df_1, how='left')
        df_3 = pd.merge(df_2, entity_poly_df, how='left')

        df_3['metal_ligand_num'] = df_3.apply(lambda x: str(x['metal_ligand_content']).count(
            '),') + 1 if not isinstance(x['metal_ligand_content'], float) else 0, axis=1)
        df_3['Modification_num'] = df_3.apply(lambda x: x['_pdbx_poly_seq_scheme.mon_id'].count(
            'X') if not isinstance(x['_pdbx_poly_seq_scheme.mon_id'], float) else np.nan, axis=1)
        df_3['seqres_len'] = df_3.apply(lambda x: len(x['_pdbx_poly_seq_scheme.mon_id']) if not isinstance(
            x['_pdbx_poly_seq_scheme.mon_id'], float) else np.nan, axis=1)
        df_3['coordinates_len'] = df_3.apply(lambda x: len(x['_pdbx_poly_seq_scheme.pdb_mon_id'].replace(
            '?', '')) if not isinstance(x['_pdbx_poly_seq_scheme.pdb_mon_id'], float) else np.nan, axis=1)

        def find_charIndex_fun(s, char): return [x for x in range(
            s.find(char), len(s)) if s[x] == char]
        df_3['Modification_index'] = df_3.apply(lambda x: find_charIndex_fun(
            x['_pdbx_poly_seq_scheme.mon_id'], 'X') if not isinstance(x['_pdbx_poly_seq_scheme.mon_id'], float) else np.nan, axis=1)
        df_3['mis_index'] = df_3.apply(lambda x: find_charIndex_fun(x['_pdbx_poly_seq_scheme.pdb_mon_id'], '?') if not isinstance(
            x['_pdbx_poly_seq_scheme.pdb_mon_id'], float) else np.nan, axis=1)

        df_3['mis_range'] = df_3.apply(lambda x: MMCIF2Dfrm.getInterval(
            x['mis_index']) if not isinstance(x['mis_index'], float) else np.nan, axis=1)
        df_3['resolution_score'] = df_3.apply(lambda x: MMCIF2Dfrm.handleResolution(x['resolution']), axis=1)

        col_list = ['pdb_id', 'chain_id', 'protein_type', 'coordinates_len']
        pro_chain_grouper = MMCIF2Dfrm.GroupER(
            col_list[0], ['polypeptide(L)', 'polypeptide(D)'], df_3, 'protein_chain_and_length')
        df_3['protein_chain_and_length'] = np.nan
        for i in df_3.index:
            pro_chain_grouper.check(df_3.loc[i, col_list[0]], (
                i, df_3.loc[i, col_list[-2]], df_3.loc[i, col_list[-1]], df_3.loc[i, col_list[1]]))
        pro_chain_grouper.output()

        if os.path.exists(outputPath):
            self.file_o(outputPath, df_3, mode='a+', header=False)
        else:
            self.file_o(outputPath, df_3)
        return df_3


if __name__ == '__main__':
    route = 'C:\\Users\\Nature\\Desktop\\LiGroup\\Filter_new_20190123\\doc_in\\spe\\'
    file_list = os.listdir(route)
    file_p_list = [route + i for i in file_list]
    mmcif_demo = MMCIF2Dfrm()
    df = mmcif_demo.mmcif_dict2dfrm(file_p_list)
    df_new = mmcif_demo.handle_mmcif_dfrm(df)
    for i in df_new.index:
        print(df_new.loc[i, ])