# @Date:   2019-08-19T19:29:29+08:00
# @Email:  1730416009@stu.suda.edu.cn
# @Filename: MMCIFplus_unit.py
# @Last modified time: 2019-08-21T19:41:49+08:00
from collections import defaultdict
import pandas as pd
import numpy as np
import os, time, requests, sys
from urllib import request, error
from retrying import retry
from multiprocessing.dummy import Pool
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
sys.path.append('./')
from Unit import Unit

class MMCIF_unit(Unit):
    CONFIG = {
        'MMCIF_OLD_FOLDER': [
            '/data1/suntt/process0606/cgc_mmcif_file/',
            '/data1/suntt/CanDriver/Data/PDB_cgc/cgc_mmcif_file/',
            '/data1/suntt/CanDriver/Data/PDB_NEW/mmcif_file/'
            ],
        'MMCIF_FOLDER': '/home/zzf/Work/SIFTS_Plus_Muta_Maps/data/mmcif_file/',
        'COMMON_COL': ['_pdbx_audit_revision_history.revision_date', '_exptl.method', '_em_3d_reconstruction.resolution', '_refine.ls_d_res_high'],
        'ENTITY_COL': ['_entity.pdbx_mutation', '_entity.id'],
        'TYPE_COL':['_entity_poly.entity_id', '_entity_poly.pdbx_strand_id', '_entity_poly.type'],
        'SEQRES_COL':['_pdbx_poly_seq_scheme.pdb_strand_id',
                 '_pdbx_poly_seq_scheme.mon_id','_pdbx_poly_seq_scheme.pdb_mon_id', '_pdbx_poly_seq_scheme.auth_mon_id',
                 '_pdbx_poly_seq_scheme.ndb_seq_num', '_pdbx_poly_seq_scheme.pdb_seq_num',
                 '_pdbx_poly_seq_scheme.auth_seq_num', '_pdbx_poly_seq_scheme.pdb_ins_code'],
        'LIGAND_COL': [
                 '_struct_conn.ptnr2_auth_asym_id','_struct_conn.ptnr2_auth_comp_id',
                 '_struct_conn.ptnr2_auth_seq_id',
                 '_struct_conn.conn_type_id',
                 '_struct_conn.ptnr1_auth_asym_id', '_struct_conn.ptnr1_auth_comp_id',
                 '_struct_conn.ptnr1_auth_seq_id'],
        'LIGAND_LIST': [
                        'ZN', 'MG', 'CA', 'FE', 'NA', 'MN', 'K', 'NI', 'CU', 'CO', 'CD', 'HG', 'PT', 'MO', 'BE', 'AL', 'BA',
                        'RU', 'SR', 'V', 'CS', 'W', 'AU', 'YB', 'LI', 'GD', 'PB', 'Y', 'TL', 'IR', 'RB', 'SM', 'AG',
                        'OS', 'PR', 'PD', 'EU', 'RH', 'RE', 'TB', 'TA', 'LU', 'HO', 'CR', 'GA', 'LA', 'SN', 'SB', 'CE',
                        'ZR', 'ER', 'TH', 'TI', 'IN', 'HF', 'SC', 'DY', 'BI', 'PA', 'PU', 'AM', 'CM', 'CF', 'GE', 'NB', 'TC',
                        'ND', 'PM', 'TM', 'PO', 'FR', 'RA', 'AC', 'NP', 'BK', 'ES', 'FM', 'MD', 'NO', 'LR', 'RF', 'DB', 'SG'],
        'HEADERS': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134'},

        }

    pdb_path_li = []

    def download_cif_file(pdbId, path):
        url = 'https://files.rcsb.org/view/%s.cif' % pdbId
        html = request.urlopen(url).read()
        html = html.decode('utf-8')
        with open(path, 'w') as fw:
            fw.write(html)
            time.sleep(2)

    def get_mmcif_file_path(self, pdbId, download=False):
        print('get_mmcif_file_path(): Working on [%s]' % pdbId)
        new_path  = '%s%s.cif' % (self.CONFIG['MMCIF_FOLDER'], pdbId)

        for path in self.CONFIG['MMCIF_OLD_FOLDER']:
            old_path = '%s%s.cif' % (path, pdbId)
            if os.path.exists(old_path):
                return old_path

        if os.path.exists(new_path):
            return new_path
        else:
            if download:
                MMCIF_unit.download_cif_file(pdbId, new_path)

            return new_path

    def check_mmcif_file(self, pdb_list):
        def find_unDownloaded_file(pdbId):
            for path in self.CONFIG['MMCIF_OLD_FOLDER']+[self.CONFIG['MMCIF_FOLDER']]:
                old_path = '%s%s.cif' % (path, pdbId)
                if os.path.exists(old_path):
                    MMCIF_unit.pdb_path_li.append(old_path)
                    return False
            return True

        unDownload = list(filter(find_unDownloaded_file, pdb_list))

        @retry(stop_max_attempt_number=3, wait_fixed=1000)
        def download_mmcif_file(pdbId):
            path = '%s%s.cif' % (MMCIF_unit.CONFIG['MMCIF_FOLDER'], pdbId)
            print('download_mmcif_file(): %s' % path)
            url = 'https://files.rcsb.org/view/%s.cif' % pdbId
            r = requests.get(url, headers=MMCIF_unit.CONFIG['HEADERS'])
            with open(path, 'wb+') as fw:
                fw.write(r.content)
                time.sleep(2)
                MMCIF_unit.pdb_path_li.append(path)

        pool = Pool(processes=20)
        pool.map(download_mmcif_file, unDownload)

    def get_mmcif_info(info_key, info_key_nli, info_dict, path):
        mmcif_dict = MMCIF2Dict(path)
        for key in info_key:

            if key in info_key_nli:
                data = mmcif_dict.get(key,np.nan)
                info_dict[key].append(data)
            else:
                data = mmcif_dict.get(key,[])
                if isinstance(data, str):
                    info_dict[key].append([data])
                    ## data = data.split(',')
                    # print(key)
                # info_dict[key].append(list(filter(lambda x :x not in '?.', data)))
                else:
                    info_dict[key].append(data)

    def get_data_from_mmcif(self, path_list, outputPath=False):
        '''
        {
            '_pdbx_audit_revision_history.revision_date': ['initial_version_time', 'newest_version_time'], # sometimes not a list
            '_entity.pdbx_mutation': ['mutation_num', 'mutation_content'], # sometimes not a list
            '_entity.id': ['entity_id_aidMuta'], # sometimes not a list
            ['_em_3d_reconstruction.resolution','_refine.ls_d_res_high']: ['resolution'], # not a lists
            '_exptl.method': ['method'], # not a list
        }

        '''
        info_dict = defaultdict(list)
        for path in path_list:
            if path[-3:] == 'cif':
                print(path)
                info_dict['pdb_id'].append(path[-8:-4])
                MMCIF_unit.get_mmcif_info(
                    MMCIF_unit.CONFIG['COMMON_COL'] + \
                    MMCIF_unit.CONFIG['ENTITY_COL'] + \
                    MMCIF_unit.CONFIG['TYPE_COL'] + \
                    MMCIF_unit.CONFIG['SEQRES_COL'] + \
                    MMCIF_unit.CONFIG['LIGAND_COL'],
                    MMCIF_unit.CONFIG['COMMON_COL'][1:],
                    info_dict,
                    path)

        # Deal with Residues in SEQRES_COL
        resides_col_li = MMCIF_unit.CONFIG['SEQRES_COL'][1:4]
        mtoTool = Unit.MultiToOne()
        for i in range(len(info_dict[resides_col_li[0]])):
            for resides_col in resides_col_li:
                info_dict[resides_col][i] = ''.join([mtoTool.multi_letter_convert_to_one_letter(j) for j in info_dict[resides_col][i]])

        get_index = lambda x, y, z: y[x[z]:x[z+1]] if len(x) != 1 and z+1 < len(x) else y[x[z]:]
        # Deal with SEQRES_COL
        pdbx_poly_key = MMCIF_unit.CONFIG['SEQRES_COL'][0]
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

            for col in MMCIF_unit.CONFIG['SEQRES_COL'][1:4]:
                info_dict[col][i] = [
                    get_index(strand_id_index, info_dict[col][i], j)
                    for j in range(len(strand_id_index))]

            for col in MMCIF_unit.CONFIG['SEQRES_COL'][4:]:
                info_dict[col][i] = [';'.join(
                    get_index(strand_id_index, info_dict[col][i], j))
                    for j in range(len(strand_id_index))]

        # Deal with LIGAND_COL: Sort the data
        ligand_col_list = MMCIF_unit.CONFIG['LIGAND_COL']
        for i in range(len(info_dict[ligand_col_list[0]])):
            ligand_col_tp = tuple(info_dict[col][i] for col in ligand_col_list)
            ligand_col_zip_li = list(zip(*ligand_col_tp))
            ligand_col_zip_li.sort()
            for col_index in range(len(ligand_col_list)):
                info_dict[ligand_col_list[col_index]][i] = [tp[col_index] for tp in ligand_col_zip_li]
        # Deal with LIGAND_COL: Group the data
        ligand_group_col = ligand_col_list[0]
        new_ligand_col_li = ['%s_index'%ligand_group_col, '%s_li'%ligand_group_col]
        self.new_ligand_col_li = new_ligand_col_li
        for i in range(len(info_dict[ligand_group_col])):
            strand_id_index = [0]
            li = info_dict[ligand_group_col][i]
            if not li:
                info_dict[new_ligand_col_li[0]].append([])
                info_dict[new_ligand_col_li[1]].append([])
                continue
            save_id = li[0]
            strand_id_li = [save_id]
            for j in range(len(li)):
                if li[j] != save_id:
                    save_id = li[j]
                    strand_id_index.append(j)
                    strand_id_li.append(save_id)
            info_dict[new_ligand_col_li[1]].append(strand_id_li)
            info_dict[new_ligand_col_li[0]].append(strand_id_index)

            for col in ligand_col_list:
                info_dict[col][i] = [
                    get_index(strand_id_index, info_dict[col][i], j)
                    for j in range(len(strand_id_index))]

        df = pd.DataFrame(info_dict)
        # Deal with the date of structure
        df['initial_version_time'] = df.apply(lambda x: x[MMCIF_unit.CONFIG['COMMON_COL'][0]][0], axis=1)
        df['newest_version_time'] = df.apply(lambda x: x[MMCIF_unit.CONFIG['COMMON_COL'][0]][-1], axis=1)
        # Deal with the mutations
        muta_count = lambda x: x.count(',')+1 if x!= '?' else 0
        df['mutation_num'] = df.apply(lambda x: [muta_count(i) for i in x['_entity.pdbx_mutation']], axis=1)
        # Deal with the resolution
        df['resolution'] = df.apply(lambda x: x[MMCIF_unit.CONFIG['COMMON_COL'][3]] if 'X-RAY DIFFRACTION' in x[MMCIF_unit.CONFIG['COMMON_COL'][1]] else x[MMCIF_unit.CONFIG['COMMON_COL'][2]], axis=1)
        # Change the columns
        df.rename(columns={MMCIF_unit.CONFIG['COMMON_COL'][1]:'method'},inplace=True)
        df.drop(columns=[MMCIF_unit.CONFIG['COMMON_COL'][0],MMCIF_unit.CONFIG['COMMON_COL'][2],MMCIF_unit.CONFIG['COMMON_COL'][3]],inplace=True)

        if os.path.exists(outputPath):
            self.file_o(outputPath, df, mode='a+',header=False)
        else:
            self.file_o(outputPath, df)
        return df

    def handle_mmcif_df(self, dfrm, outputPath=False):
        def get_sub_df(df, i, spe_col_li, common_col_li):
            try:
                a = pd.DataFrame({key: df.loc[i,key] for key in spe_col_li})
            except Exception as e:
                print(pdb, e)
                a = pd.DataFrame({key: [df.loc[i,key]] for key in spe_col_li})

            for common_col in common_col_li:
                try:
                    a[common_col] = df.loc[i, common_col]
                except Exception as e:
                    print(e)
                    a[common_col] = ','.join(df.loc[i, common_col])
            return a

        def sub_handle_df(df, spe_col_li, common_col_li):
            df_li = []
            for i in df.index:
                df_li.append(get_sub_df(df, i, spe_col_li, common_col_li))
            return pd.concat(df_li, ignore_index=True)

        entity_poly_df = sub_handle_df(dfrm, MMCIF_unit.CONFIG['ENTITY_COL']+['mutation_num'], ['pdb_id'])
        type_poly_df = sub_handle_df(dfrm, MMCIF_unit.CONFIG['TYPE_COL'], ['pdb_id'])
        basic_df = sub_handle_df(dfrm, MMCIF_unit.CONFIG['SEQRES_COL'], ['pdb_id', 'method', 'initial_version_time', 'newest_version_time', 'resolution'])
        ligand_df = sub_handle_df(dfrm, MMCIF_unit.CONFIG['LIGAND_COL']+self.new_ligand_col_li, ['pdb_id'])

        new_type_poly_df = type_poly_df.drop(MMCIF_unit.CONFIG['TYPE_COL'][1], axis=1).join(type_poly_df[MMCIF_unit.CONFIG['TYPE_COL'][1]].str.split(',', expand=True).stack().reset_index(level=1, drop=True).rename('chain_id'))

        entity_poly_df.rename(columns={'_entity.pdbx_mutation': 'mutation_content', '_entity.id': 'entity_id'}, inplace=True)
        new_type_poly_df.rename(columns={'_entity_poly.entity_id': 'entity_id', '_entity_poly.type': 'protein_type'}, inplace=True)
        basic_df.rename(columns={'_pdbx_poly_seq_scheme.pdb_strand_id':'chain_id'}, inplace=True)
        ligand_df.rename(columns={self.new_ligand_col_li[1]:'chain_id'}, inplace=True)

        df_1 = pd.merge(basic_df, ligand_df, how='left')
        df_2 = pd.merge(new_type_poly_df, df_1, how='left')
        df_3 = pd.merge(df_2, entity_poly_df, how='left')

        if os.path.exists(outputPath):
            self.file_o(outputPath, df_3, mode='a+',header=False)
        else:
            self.file_o(outputPath, df_3)
        return df_3

    def script_fun(self, pdb_list, outputPath_li, chunksize=100):
        for i in range(0, len(pdb_list), chunksize):
            chunk_li = pdb_list[i:i+chunksize]
            MMCIF_unit.pdb_path_li = []
            self.check_mmcif_file(chunk_li)
            chunk_df = self.get_data_from_mmcif(MMCIF_unit.pdb_path_li, outputPath=outputPath_li[0])
            self.handle_mmcif_df(chunk_df, outputPath=outputPath_li[1])



if __name__ == '__main__':
    route = 'C:\\Users\\Nature\\Desktop\\LiGroup\\Filter_new_20190123\\doc_in\\'
    file_list = os.listdir(route)
    file_p_list = [route+i for i in file_list]
    mmcif_demo = MMCIF_unit()
    df = mmcif_demo.get_data_from_mmcif(file_p_list)

    df_new = mmcif_demo.handle_mmcif_df(df)

    for i in df.index:
        print(df_new.loc[i,])