"""Simple hover tooltip for Tk widgets.

Usage:
    Tooltip(my_button, 'Helpful description')

Shows after DELAY_MS on <Enter>; hides on <Leave> or any click. Uses an
undecorated Toplevel so the tip floats over the rest of the UI.
"""

import tkinter as tk


class Tooltip:
    DELAY_MS = 500

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._tipwindow = None
        self._after_id = None
        # add='+' so we don't clobber existing <Enter>/<Leave> handlers.
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f'+{x}+{y}')
        tk.Label(
            tw, text=self.text, justify='left',
            background='#ffffe0', relief='solid', borderwidth=1,
            font=('TkDefaultFont', 9), padx=4, pady=2,
        ).pack()
        self._tipwindow = tw

    def _hide(self, _event=None):
        self._cancel()
        if self._tipwindow is not None:
            self._tipwindow.destroy()
            self._tipwindow = None
