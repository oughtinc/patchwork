"""Basic Functional HCH"""

import sys

from .datastore import Datastore
from .scheduling import Scheduler
from .interface import UserInterface


def main(argv):
    d = Datastore()
    s = Scheduler()
    i = UserInterface(d, s)
    i.cmdloop()

if __name__ == "__main__":
    main(sys.argv)

