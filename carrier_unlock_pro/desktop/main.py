import json, subprocess, tkinter as tk
from tkinter import ttk

def detect():
    try:
        result = subprocess.run(['adb','devices','-l'],capture_output=True,text=True,timeout=10,check=True)
        lines = result.stdout.splitlines()[1:]
        devices = [line for line in lines if '\tdevice' in line]
        output.delete('1.0','end')
        output.insert('end', json.dumps({'authorized_android_devices':devices,'note':'ADB requires USB debugging and user authorization. iPhone detection is not implemented.'},indent=2))
    except FileNotFoundError:
        output.delete('1.0','end'); output.insert('end','ADB not installed. Install Android Platform Tools and add adb to PATH.')
    except (subprocess.SubprocessError, OSError) as exc:
        output.delete('1.0','end'); output.insert('end',f'Device scan failed: {exc}')

root=tk.Tk(); root.title('Carrier Unlock Pro — Device Diagnostics'); root.geometry('680x400')
ttk.Label(root,text='Carrier Unlock Pro — Authorized Device Detection',font=('Arial',15,'bold')).pack(pady=18)
ttk.Button(root,text='Scan Android Devices (ADB)',command=detect).pack(pady=10)
output=tk.Text(root,wrap='word');output.pack(fill='both',expand=True,padx=15,pady=15)
root.mainloop()
