import subprocess
import sys
import os


if len(sys.argv) < 2:
    print("Usage: " + os.path.split(__file__)[1] + " your_script.py [arg1 arg2 ...]")
    sys.exit(1)

script_name = sys.argv[1]
arguments = sys.argv[2:]

try:
    subprocess.run(['py', '-m', 'pydblclick', script_name] + arguments, check=True)
except subprocess.CalledProcessError as e:
    print(f"Command failed with error: {e}")
except FileNotFoundError:
    print("The 'py' command is not found. Make sure Python is installed and added to your system PATH.")
