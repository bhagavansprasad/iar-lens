# ---------------------------------------------------------------------------
# iar-lens | config.py
# Central configuration — all paths are relative to project root
# ---------------------------------------------------------------------------

# IAR source files (older version → newer version)
SOURCE_IAR = "flow-dump/INT303_INVENTOR_EI_RECONCIL_03.00.0001.iar.zip"
TARGET_IAR = "flow-dump/INT303_INVENTOR_EI_RECONCIL_03.00.0011.iar.zip"

# Workspace — where IAR files get extracted during processing
WORKSPACE_DIR = "workspace/"

# Output — where delta.json is written
OUTPUT_DIR = "output/"

# Retain extracted workspace after processing (True = keep, False = cleanup)
KEEP_WORKSPACE = True

# Logging level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL = "INFO"
