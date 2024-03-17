import os
import re
import sys

# super simple helper to inject the user provided environment variables into the
# existing docker-compose.yml file

# take filenames from command line argument
if len(sys.argv) < 3:
    print("Usage: inject-env.py <filename> <user_env>")
    sys.exit(1)
filename = sys.argv[1]
user_env = sys.argv[2]

if not os.path.exists(filename):
    print(f"File {filename} not found")
    sys.exit(1)
if not os.path.exists(user_env):
    print(f"File {user_env} not found")
    sys.exit(1)

# copy original file just in case
os.rename(filename, filename + ".org")

# grab the env provided by the user
with open(user_env, "r") as u:
    user_env = u.read()

# read the existing file and inject the user env
# obviously the spacing and syntax of the user env must match the yml syntax
with open(filename + ".org", "r") as fin:
    lines = fin.read()
new_lines = re.sub(
    r"^      # USER_PROVIDED_ENV_START.*      # USER_PROVIDED_ENV_END",
    f"      # USER_PROVIDED_ENV_START\n{user_env}      # USER_PROVIDED_ENV_END",
    lines,
    flags=re.MULTILINE | re.DOTALL,
)
with open(filename, "w") as fout:
    fout.write(new_lines)
