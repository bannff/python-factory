import sys
from .server import mcp

def main():
    """Entry point for the CLI."""
    mcp.run(sys.argv[1:])

if __name__ == "__main__":
    main()
