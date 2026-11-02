import tkinter as tk
from gui import App

import metadata
import duplicates
import sorter
import reports


def main():


    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()