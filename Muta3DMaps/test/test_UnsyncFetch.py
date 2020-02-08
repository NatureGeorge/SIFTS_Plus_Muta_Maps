import pytest
from Muta3DMaps.core.retrieve.fetchFiles import UnsyncFetch

DEMO = [
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/1a01',
     None, '1a01_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/2xyn',
     None, '2xyn_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/1miu',
     None, '1miu_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/2hev',
     None, '2hev_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/3g96',
     None, '3g96_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/molecules/6lu7',
     None, '6lu7_molecules.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/secondary_structure/',
     '1a01,2xyn,2hev', '1a01,2xyn,2hev_secondary_structure.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/1a01',
     None, '1a01_residue_listing.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/2xyn',
     None, '2xyn_residue_listing.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/1miu',
     None, '1miu_residue_listing.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/2hev',
     None, '2hev_residue_listing.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pppp',
     None, 'pppp_pppp.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/3g96',
     None, '3g96_residue_listing.json'),
    ('https://www.ebi.ac.uk/pdbe/api/pdb/entry/residue_listing/6lu7',
     None, '6lu7_residue_listing.json')]

def test_main():
    try:
        return UnsyncFetch.main(r'./data/', DEMO, 8)
    except Exception:
        return -1

def answer_main():
    res = test_main()
    assert res == len(DEMO) and len([i for i in res if i is None]) == 2