import warnings

# Quiet ResourceWarning about unclosed sqlite3 connections while we audit and
# fix remaining import-time DB opens. This keeps test output clean while we
# perform code-level fixes. Once the codebase is fully cleaned we can remove
# this filter.
warnings.filterwarnings("ignore", category=ResourceWarning)
