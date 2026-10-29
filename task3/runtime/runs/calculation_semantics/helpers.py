import sys,importlib.util,json,hashlib
from pathlib import Path
W=Path(__file__).resolve().parents[2];O=Path(__file__).resolve().parent
sys.path.insert(0,str(W/'runs/nonnegative_strategies'))
import new_strategies as prev
old=prev.old;raw=prev.raw;ROOT=old.ROOT
BASE=W/'runs/strategy_engine/L15_loss_partition';MODEL=W/'runs/l15plus_feedback_20261015'
rows=old.rows;read=old.read;save=old.save;sha=old.sha;same=old.same
local=prev.local;ds=prev.ds;frame=prev.frame;val=prev.val
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
