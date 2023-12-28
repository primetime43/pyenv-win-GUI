# Author: primetime43
# GitHub: https://github.com/primetime43

import tkinter as tk
from tkinter import ttk
import subprocess
import os
import threading

def run_ps1(uninstall=False):
    # This function handles the installation and uninstallation of pyenv

    # Skip the check if pyenv is installed when uninstalling
    if not uninstall:
        # Check if pyenv is installed by running a PowerShell command
        try:
            version = subprocess.check_output(['powershell', '-Command', 'pyenv --version'])
            output_text.insert(tk.END, "pyenv is already installed.\n")
            output_text.insert(tk.END, version.decode() + "\n")
            output_text.see(tk.END)
            return  # Return immediately if pyenv is already installed
        except subprocess.CalledProcessError:
            pass  # If pyenv is not installed, continue with the installation

    # If pyenv is not installed and uninstall is requested, display message
    if uninstall:
        try:
            subprocess.check_output(['powershell', '-Command', 'pyenv --version'])
        except subprocess.CalledProcessError:
            output_text.insert(tk.END, "pyenv is not installed, so it cannot be uninstalled.\n")
            output_text.see(tk.END)
            return

    # Check if the installation script is present, if not, download it
    if not os.path.exists("./install-pyenv-win.ps1"):
        ps_command = 'Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"'
        command = ['powershell', '-Command', ps_command]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Prepare and execute the installation or uninstallation command
    if uninstall:
        output_text.insert(tk.END, "Starting uninstallation...\n")
        command = ['powershell', '-Command', '&"./install-pyenv-win.ps1" -Uninstall']
    else:
        output_text.insert(tk.END, "Starting installation...\n")
        command = ['powershell', '-Command', '&"./install-pyenv-win.ps1"']

    output_text.see(tk.END)

    # Run the command in a subprocess and capture the output
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Read and display the output from the subprocess
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            output_text.insert(tk.END, output.decode())
            output_text.see(tk.END)
    rc = process.poll()

def install_update():
    # Start a new thread for installing or updating pyenv
    threading.Thread(target=run_ps1, args=(False,)).start()

def uninstall():
    # Start a new thread for uninstalling pyenv
    threading.Thread(target=run_ps1, args=(True,)).start()
    
def clear_output():
    # Clear the output text area
    output_text.delete('1.0', tk.END)

def run_command():
    # Run a pyenv command using PowerShell and display the output
    command = ['powershell', '-Command', f'pyenv {command_var.get()} {params_entry.get()}']
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output_text.insert(tk.END, result.stdout.decode())
    output_text.see(tk.END)

# Create the main window
root = tk.Tk()
root.title("pyenv-win GUI")  # Set the title of the window

# Create the Install/Update button with left padding
install_button = tk.Button(root, text="Install/Update pyenv-win", command=install_update)
install_button.grid(row=0, column=0, sticky='w', pady=(10, 5), padx=(10, 0))  # Add 10 pixels of padding to the left

# Create the Uninstall button with left padding
uninstall_button = tk.Button(root, text="Uninstall pyenv-win", command=uninstall)
uninstall_button.grid(row=1, column=0, sticky='w', pady=5, padx=(10, 0))  # Add 10 pixels of padding to the left

# List of commands for the dropdown menu
commands = ['commands', 'duplicate', 'local', 'global', 'shell', 'install', 'uninstall', 'update', 'rehash', 'vname', 'version', 'version-name', 'versions', 'exec', 'which', 'whence']

# Create a variable for the selected command
command_var = tk.StringVar(root)
command_var.set(commands[0])  # Set the default option

# Create the dropdown menu for the commands
command_menu = ttk.Combobox(root, textvariable=command_var, values=commands)
command_menu.grid(row=2, column=0, pady=5)  # Place the dropdown menu in the grid

# Create a frame for the parameters input
params_frame = tk.Frame(root)
params_frame.grid(row=3, column=0)  # Place the frame in the grid

# Create a label for the parameters input
params_label = tk.Label(params_frame, text="Parameters:")
params_label.pack(side=tk.LEFT)  # Place the label in the frame

# Create the parameters input box
params_entry = tk.Entry(params_frame)
params_entry.pack(side=tk.LEFT)  # Place the input box in the frame

# Create the Run Command button
run_button = tk.Button(root, text="Run Command", command=run_command)
run_button.grid(row=4, column=0, pady=5)  # Place the button in the grid

# Create the output text box
output_text = tk.Text(root)
output_text.grid(row=5, column=0, sticky='nsew', pady=5)  # Place the text box in the grid

# Create the scrollbar for the output text box
scrollbar = tk.Scrollbar(root, command=output_text.yview)
scrollbar.grid(row=5, column=1, sticky='ns')  # Place the scrollbar in the grid

# Link the scrollbar to the output text box
output_text['yscrollcommand'] = scrollbar.set

# Create the Clear Output button
clear_button = tk.Button(root, text="Clear Output", command=clear_output)
clear_button.grid(row=6, column=0, pady=(5, 10))  # Place the button in the grid

# Start the main event loop
root.mainloop()