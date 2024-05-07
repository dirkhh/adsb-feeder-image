import os
import re
import sys

# super simple helper to inject the user provided environment variables into the
# existing docker-compose.yml file

# take filenames from command line argument
if len(sys.argv) < 3:
    print("Usage: inject-env.py <user_env> [yml file]...")
    sys.exit(1)
user_env = sys.argv[1]
filenames = sys.argv[2:]

if not os.path.exists(user_env):
    print(f"user_env file {user_env} not found")
    sys.exit(1)

# grab the env provided by the user
with open(user_env, "r") as u:
    lines_to_add = u.read()


for filename in filenames:
    #print(f"processing {filename}")
    if not os.path.exists(filename):
        print(f"yml file {filename} not found")
        sys.exit(1)

    # read the existing file
    with open(filename, "r") as fin:
        lines = fin.read()

    # inject the user env
    # obviously the spacing and syntax of the user env must match the yml syntax
    new_lines = re.sub(
        r"^      # USER_PROVIDED_ENV_START.*      # USER_PROVIDED_ENV_END",
        f"      # USER_PROVIDED_ENV_START\n{lines_to_add}      # USER_PROVIDED_ENV_END",
        lines,
        flags=re.MULTILINE | re.DOTALL,
    )
    with open(filename, "w") as fout:
        fout.write(new_lines)
