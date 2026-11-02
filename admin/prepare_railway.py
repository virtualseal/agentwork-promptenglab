"""Retired shared-credential package. Kept only to reject historical entry points."""
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
ROOT=Path('/Library/Application Support/CredentialProxy')
def prepare(*args,**kwargs):
    raise ValueError('Legacy shared-workspace Railway staging is disabled; use admin.prepare_personal_railway')
if __name__=='__main__':prepare()
