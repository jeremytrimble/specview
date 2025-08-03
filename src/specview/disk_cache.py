import diskcache
from platformdirs import user_cache_dir


dcache = diskcache.Cache( directory=user_cache_dir("specview", "jeremytrimble") )