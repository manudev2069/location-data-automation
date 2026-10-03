# Run this file with VS Code's ▶ Run Python File button.
# It opens a GUI where you can select ONE OR MULTIPLE CSV files.

import tkinter as tk
from app import MultiFileAutomationApp

if __name__ == "__main__":
    root = tk.Tk()
    MultiFileAutomationApp(root)
    root.mainloop()
