"""
Enhanced Basic GUI Image Editor (Level 1 upgrades)

Features added:
- Brightness slider
- Contrast slider
- Sharpness slider
- Blur slider + Apply Blur
- Crop tool (mouse drag to select and crop)
- Zoom In / Zoom Out
- Thumbnails: Original & Current (click thumbnail to focus)
- All previous features retained (Open, Save As, Quick Save, Grayscale, Rotate, Flip, Resize, Undo, Reset)

Usage:
    pip install pillow
    python image_editor.py
"""

import os
import math
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk, ImageOps, ImageEnhance, ImageFilter

# --- Configuration ---
MAX_DISPLAY_WIDTH = 900
MAX_DISPLAY_HEIGHT = 600
THUMB_SIZE = (160, 100)
DEFAULT_SAVE_FOLDER = os.path.join("..", "output", "edited_images")  # relative to src/

# --- ensure default save folder ---
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DEFAULT_SAVE_FOLDER_ABS = os.path.abspath(os.path.join(SCRIPT_DIR, DEFAULT_SAVE_FOLDER))
    os.makedirs(DEFAULT_SAVE_FOLDER_ABS, exist_ok=True)
except Exception:
    DEFAULT_SAVE_FOLDER_ABS = None


class ImageEditorApp:
    def __init__(self, root):
        self.root = root
        root.title("Enhanced Basic GUI Image Editor")
        root.geometry("1200x800")

        # --- state ---
        self.original_image = None   # original PIL Image (immutable copy)
        self.current_image = None    # working PIL Image
        self._undo_image = None      # single-step undo
        self.photo_image = None      # ImageTk.PhotoImage for canvas
        self.current_filepath = None

        # Display mapping state
        self.display_scale = 1.0
        self.display_w = 0
        self.display_h = 0
        self.display_offset_x = 0
        self.display_offset_y = 0

        # Crop state
        self.crop_mode = False
        self.crop_start = None  # (x,y) in canvas coords
        self.crop_rect_id = None

        # --- Layout: left toolbar, center canvas, right thumbnails & sliders ---
        top_frame = tk.Frame(root)
        top_frame.pack(fill=tk.X, padx=6, pady=6)

        # File & primary buttons
        tk.Button(top_frame, text="Open", width=10, command=self.open_image).pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text="Save As", width=10, command=self.save_image_as).pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text="Save (default folder)", width=18, command=self.save_quick).pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text="Undo", width=8, command=self.undo).pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text="Reset", width=10, command=self.reset_image).pack(side=tk.LEFT, padx=4)
        tk.Button(top_frame, text="Exit", width=8, command=root.quit).pack(side=tk.RIGHT, padx=4)

        # Secondary operations row
        ops_frame = tk.Frame(root)
        ops_frame.pack(fill=tk.X, padx=6, pady=4)

        tk.Button(ops_frame, text="Grayscale", width=10, command=self.convert_grayscale).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Rotate ⟲", width=10, command=lambda: self.rotate_image(-90)).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Rotate ⟳", width=10, command=lambda: self.rotate_image(90)).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Rotate by angle", width=14, command=self.rotate_by_angle).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Flip H", width=8, command=lambda: self.flip_image("H")).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Flip V", width=8, command=lambda: self.flip_image("V")).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Resize", width=8, command=self.resize_image).pack(side=tk.LEFT, padx=4)

        # Add Crop toggle and Zoom controls
        tk.Button(ops_frame, text="Crop", width=8, command=self.toggle_crop_mode).pack(side=tk.LEFT, padx=8)
        tk.Button(ops_frame, text="Zoom In", width=8, command=lambda: self.zoom(1.25)).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Zoom Out", width=8, command=lambda: self.zoom(0.8)).pack(side=tk.LEFT, padx=4)
        tk.Button(ops_frame, text="Fit to window", width=12, command=self.fit_to_window).pack(side=tk.LEFT, padx=4)

        # Main content frame
        content = tk.Frame(root)
        content.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Canvas in center
        canvas_frame = tk.Frame(content)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="#f2f2f2", width=MAX_DISPLAY_WIDTH, height=MAX_DISPLAY_HEIGHT)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_down)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_up)

        # Right-side controls (thumbnails + filters)
        right_frame = tk.Frame(content, width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(8,0))

        # Thumbnails area
        thumb_label = tk.Label(right_frame, text="Thumbnails")
        thumb_label.pack(anchor=tk.NW)
        self.thumb_canvas = tk.Canvas(right_frame, width=THUMB_SIZE[0]+20, height=THUMB_SIZE[1]*2 + 60, bg="#fff")
        self.thumb_canvas.pack(pady=6)
        # clickable thumbnail placeholders
        self.thumb_orig_id = None
        self.thumb_curr_id = None

        # Sliders area
        sliders_label = tk.Label(right_frame, text="Adjustments")
        sliders_label.pack(anchor=tk.NW, pady=(12,0))

        # Brightness
        tk.Label(right_frame, text="Brightness").pack(anchor=tk.W, padx=6)
        self.brightness_slider = tk.Scale(right_frame, from_=0.2, to=2.0, resolution=0.05, orient=tk.HORIZONTAL, length=260, command=self._on_adjustment_change)
        self.brightness_slider.set(1.0)
        self.brightness_slider.pack(padx=6, pady=4)

        # Contrast
        tk.Label(right_frame, text="Contrast").pack(anchor=tk.W, padx=6)
        self.contrast_slider = tk.Scale(right_frame, from_=0.2, to=2.0, resolution=0.05, orient=tk.HORIZONTAL, length=260, command=self._on_adjustment_change)
        self.contrast_slider.set(1.0)
        self.contrast_slider.pack(padx=6, pady=4)

        # Sharpness
        tk.Label(right_frame, text="Sharpness").pack(anchor=tk.W, padx=6)
        self.sharpness_slider = tk.Scale(right_frame, from_=0.0, to=2.0, resolution=0.05, orient=tk.HORIZONTAL, length=260, command=self._on_adjustment_change)
        self.sharpness_slider.set(1.0)
        self.sharpness_slider.pack(padx=6, pady=4)

        # Blur
        tk.Label(right_frame, text="Blur radius (px)").pack(anchor=tk.W, padx=6)
        self.blur_slider = tk.Scale(right_frame, from_=0, to=10, resolution=1, orient=tk.HORIZONTAL, length=260)
        self.blur_slider.set(0)
        self.blur_slider.pack(padx=6, pady=4)
        tk.Button(right_frame, text="Apply Blur", width=18, command=self.apply_blur).pack(padx=6, pady=(2,10))

        # Reset adjustments button
        tk.Button(right_frame, text="Reset Adjustments", width=18, command=self.reset_adjustments).pack(padx=6, pady=(6,10))

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("No image loaded.")
        status_bar = tk.Label(root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Shortcuts
        root.bind("<Control-o>", lambda e: self.open_image())
        root.bind("<Control-s>", lambda e: self.save_image_as())
        root.bind("<Control-q>", lambda e: root.quit())
        root.bind("<Control-z>", lambda e: self.undo())

    # -------------------------
    # Utility & status helpers
    # -------------------------
    def set_status(self, text: str):
        self.status_var.set(text)

    def _store_undo(self):
        if self.current_image is not None:
            try:
                self._undo_image = self.current_image.copy()
            except Exception:
                self._undo_image = None

    # -------------------------
    # File operations
    # -------------------------
    def open_image(self):
        path = filedialog.askopenfilename(
            title="Open image",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tiff"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Open error", f"Failed to open image:\n{e}")
            return

        self.original_image = img.copy()
        self.current_image = img
        self._undo_image = None
        self.current_filepath = path

        # reset adjustments and zoom
        self.reset_adjustments()
        self.fit_to_window()
        self.display_image()
        self._update_thumbnails()
        self.set_status(f"Opened: {os.path.basename(path)} — {img.width}x{img.height}")

    def save_image_as(self):
        if self.current_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return
        initial = os.path.splitext(os.path.basename(self.current_filepath or "image"))[0] if self.current_filepath else "edited_image"
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=initial + "_edited.png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg;*.jpeg"), ("BMP", "*.bmp"), ("TIFF", "*.tiff"), ("All files", "*.*")]
        )
        if not path:
            return
        self._save_to_path(path)

    def save_quick(self):
        if self.current_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return
        base_name = os.path.splitext(os.path.basename(self.current_filepath or "image"))[0]
        if DEFAULT_SAVE_FOLDER_ABS is None:
            messagebox.showinfo("Save error", "Default save folder not available.")
            return
        idx = 1
        while True:
            filename = f"{base_name}_edited_{idx}.png"
            fullpath = os.path.join(DEFAULT_SAVE_FOLDER_ABS, filename)
            if not os.path.exists(fullpath):
                break
            idx += 1
        self._save_to_path(fullpath)

    def _save_to_path(self, path):
        try:
            save_img = self.current_image
            if path.lower().endswith((".jpg", ".jpeg")) and save_img.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", save_img.size, (255, 255, 255))
                bg.paste(save_img, mask=save_img.split()[-1])
                save_img = bg
            save_img.save(path)
            self.set_status(f"Saved: {os.path.basename(path)}")
            messagebox.showinfo("Saved", f"Image saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save image:\n{e}")

    # -------------------------
    # Display & mapping
    # -------------------------
    def fit_to_window(self):
        """Reset zoom so image fits into display area."""
        if self.current_image is None:
            return
        w, h = self.current_image.size
        max_w, max_h = MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT
        scale = min(max_w / w, max_h / h, 1.0)
        self.display_scale = scale
        self.display_w = int(w * self.display_scale)
        self.display_h = int(h * self.display_scale)
        # center offsets
        self.display_offset_x = (max_w - self.display_w) // 2
        self.display_offset_y = (max_h - self.display_h) // 2

    def zoom(self, factor: float):
        """Zoom the displayed image by factor (affects display_scale only)."""
        if self.current_image is None:
            return
        # update display scale but limit extremes
        new_scale = self.display_scale * factor
        new_scale = max(0.1, min(new_scale, 6.0))
        self.display_scale = new_scale
        w, h = self.current_image.size
        self.display_w = int(w * self.display_scale)
        self.display_h = int(h * self.display_scale)
        self.display_offset_x = max(0, (MAX_DISPLAY_WIDTH - self.display_w) // 2)
        self.display_offset_y = max(0, (MAX_DISPLAY_HEIGHT - self.display_h) // 2)
        self.display_image()

    def display_image(self):
        """Scale current_image according to display_scale and show on canvas."""
        if self.current_image is None:
            self.canvas.delete("all")
            return

        w, h = self.current_image.size
        # compute display size based on display_scale but ensure not exceeding max display box
        self.display_w = int(w * self.display_scale)
        self.display_h = int(h * self.display_scale)
        # safety clamp
        if self.display_w > MAX_DISPLAY_WIDTH or self.display_h > MAX_DISPLAY_HEIGHT:
            scale = min(MAX_DISPLAY_WIDTH / w, MAX_DISPLAY_HEIGHT / h)
            self.display_w = int(w * scale)
            self.display_h = int(h * scale)
            self.display_scale = scale

        disp_img = self.current_image.resize((self.display_w, self.display_h), Image.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(disp_img)
        self.canvas.config(width=MAX_DISPLAY_WIDTH, height=MAX_DISPLAY_HEIGHT)
        self.canvas.delete("all")
        x = (MAX_DISPLAY_WIDTH - self.display_w) // 2
        y = (MAX_DISPLAY_HEIGHT - self.display_h) // 2
        self.display_offset_x = x
        self.display_offset_y = y
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo_image)
        # draw border
        self.canvas.create_rectangle(x - 1, y - 1, x + self.display_w + 1, y + self.display_h + 1, outline="#666")

    # -------------------------
    # Thumbnails area
    # -------------------------
    def _update_thumbnails(self):
        """Draw small thumbnails of original and current images in the thumbnail canvas."""
        self.thumb_canvas.delete("all")
        # original thumbnail
        if self.original_image is not None:
            orig_thumb = self.original_image.copy()
            orig_thumb.thumbnail(THUMB_SIZE, Image.LANCZOS)
            self.orig_thumb_tk = ImageTk.PhotoImage(orig_thumb)
            self.thumb_canvas.create_text(10, 10, anchor=tk.NW, text="Original", font=("Arial", 9, "bold"))
            self.thumb_canvas.create_image(10, 28, anchor=tk.NW, image=self.orig_thumb_tk, tags="orig")
            self.thumb_canvas.create_rectangle(8, 26, 8 + THUMB_SIZE[0] + 4, 26 + THUMB_SIZE[1] + 4, outline="#888")
            self.thumb_canvas.tag_bind("orig", "<Button-1>", lambda e: self._on_thumb_click("orig"))
        # current thumbnail
        if self.current_image is not None:
            curr_thumb = self.current_image.copy()
            curr_thumb.thumbnail(THUMB_SIZE, Image.LANCZOS)
            self.curr_thumb_tk = ImageTk.PhotoImage(curr_thumb)
            y_off = THUMB_SIZE[1] + 44
            self.thumb_canvas.create_text(10, y_off - 18, anchor=tk.NW, text="Current", font=("Arial", 9, "bold"))
            self.thumb_canvas.create_image(10, y_off, anchor=tk.NW, image=self.curr_thumb_tk, tags="curr")
            self.thumb_canvas.create_rectangle(8, y_off - 2, 8 + THUMB_SIZE[0] + 4, y_off + THUMB_SIZE[1] + 2, outline="#888")
            self.thumb_canvas.tag_bind("curr", "<Button-1>", lambda e: self._on_thumb_click("curr"))

    def _on_thumb_click(self, which):
        """Clicking original restores original display; clicking current just refocuses."""
        if which == "orig" and self.original_image is not None:
            # switch current to original (not permanent; store undo)
            self._store_undo()
            self.current_image = self.original_image.copy()
            self.fit_to_window()
            self.reset_adjustments()
            self.display_image()
            self._update_thumbnails()
            self.set_status("Reverted to original (thumbnail).")
        elif which == "curr":
            self.fit_to_window()
            self.display_image()
            self.set_status("Focused current image (thumbnail).")

    # -------------------------
    # Adjustments handlers
    # -------------------------
    def _on_adjustment_change(self, _=None):
        """Apply brightness/contrast/sharpness non-destructively on display by working on current_image copy."""
        if self.current_image is None:
            return
        try:
            # We apply adjustments to the _live_ image for preview, but keep the actual current_image as
            # the source. To make adjustment permanent, user can call Save or perform another operation.
            base = self.current_image.copy()

            # brightness
            b = self.brightness_slider.get()
            if abs(b - 1.0) > 1e-6:
                base = ImageEnhance.Brightness(base).enhance(b)

            # contrast
            c = self.contrast_slider.get()
            if abs(c - 1.0) > 1e-6:
                base = ImageEnhance.Contrast(base).enhance(c)

            # sharpness
            s = self.sharpness_slider.get()
            if abs(s - 1.0) > 1e-6:
                base = ImageEnhance.Sharpness(base).enhance(s)

            # keep these preview results as a temp display (do not change current_image)
            self._preview_image = base
            # display preview (but keep mapping relative to base current_image)
            self._display_preview(base)
        except Exception as e:
            # non-fatal — ignore preview errors
            print("Adjustment preview error:", e)

    def _display_preview(self, pil_img):
        """Display a PIL image for preview without changing self.current_image."""
        w, h = pil_img.size
        # scale preview image to display_scale so user sees approximate result
        disp_w = int(w * self.display_scale)
        disp_h = int(h * self.display_scale)
        # safety clamp
        if disp_w > MAX_DISPLAY_WIDTH or disp_h > MAX_DISPLAY_HEIGHT:
            scale = min(MAX_DISPLAY_WIDTH / w, MAX_DISPLAY_HEIGHT / h)
            disp_w = int(w * scale)
            disp_h = int(h * scale)
        disp_img = pil_img.resize((disp_w, disp_h), Image.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(disp_img)
        self.canvas.delete("all")
        x = (MAX_DISPLAY_WIDTH - disp_w) // 2
        y = (MAX_DISPLAY_HEIGHT - disp_h) // 2
        self.display_offset_x = x
        self.display_offset_y = y
        self.display_w = disp_w
        self.display_h = disp_h
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo_image)
        self.canvas.create_rectangle(x - 1, y - 1, x + disp_w + 1, y + disp_h + 1, outline="#666")
        # if in crop mode and user is dragging, draw that rect
        if self.crop_rect_id and self.crop_start:
            # redrawing handled by crop handlers

            pass

    def apply_blur(self):
        if self.current_image is None:
            return
        radius = int(self.blur_slider.get())
        if radius <= 0:
            messagebox.showinfo("Blur", "Set blur radius > 0.")
            return
        self._store_undo()
        try:
            self.current_image = self.current_image.filter(ImageFilter.GaussianBlur(radius=radius))
            # after applying blur, refresh thumbnails and display
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status(f"Applied Gaussian blur radius {radius}px.")
        except Exception as e:
            messagebox.showerror("Blur error", f"Failed to apply blur:\n{e}")

    def reset_adjustments(self):
        """Resets sliders to neutral and refresh display from current_image (without changing image)."""
        self.brightness_slider.set(1.0)
        self.contrast_slider.set(1.0)
        self.sharpness_slider.set(1.0)
        self.blur_slider.set(0)
        # display the base current_image
        self.display_image()

    # -------------------------
    # Image operations (permanent)
    # -------------------------
    def convert_grayscale(self):
        if self.current_image is None:
            return
        self._store_undo()
        try:
            if self.current_image.mode in ("RGBA", "LA"):
                rgba = self.current_image.convert("RGBA")
                gray = ImageOps.grayscale(rgba)
                alpha = rgba.split()[-1]
                self.current_image = Image.merge("RGBA", (gray, gray, gray, alpha))
            else:
                self.current_image = ImageOps.grayscale(self.current_image).convert("RGB")
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status("Converted to grayscale.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to convert to grayscale:\n{e}")

    def rotate_image(self, angle):
        if self.current_image is None:
            return
        self._store_undo()
        try:
            self.current_image = self.current_image.rotate(angle, expand=True)
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status(f"Rotated {angle}°.")
        except Exception as e:
            messagebox.showerror("Rotate error", f"Failed to rotate image:\n{e}")

    def rotate_by_angle(self):
        if self.current_image is None:
            return
        angle = simpledialog.askfloat("Rotate", "Enter angle in degrees (positive clockwise):", minvalue=-360, maxvalue=360)
        if angle is None:
            return
        self._store_undo()
        try:
            self.current_image = self.current_image.rotate(-angle, expand=True)
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status(f"Rotated by {angle}°.")
        except Exception as e:
            messagebox.showerror("Rotate error", f"Failed to rotate image:\n{e}")

    def flip_image(self, mode: str):
        if self.current_image is None:
            return
        self._store_undo()
        try:
            if mode == "H":
                self.current_image = ImageOps.mirror(self.current_image)
            else:
                self.current_image = ImageOps.flip(self.current_image)
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status("Flipped image.")
        except Exception as e:
            messagebox.showerror("Flip error", f"Failed to flip image:\n{e}")

    def resize_image(self):
        if self.current_image is None:
            return
        choice = simpledialog.askstring("Resize", "Enter percentage (e.g. 50 for 50%) or 'WxH' (e.g. 800x600):")
        if not choice:
            return
        self._store_undo()
        try:
            w, h = self.current_image.size
            if "x" in choice or "X" in choice:
                parts = choice.lower().split("x")
                nw, nh = int(parts[0]), int(parts[1])
            else:
                pct = float(choice)
                factor = pct / 100.0
                nw, nh = max(1, int(w * factor)), max(1, int(h * factor))
            self.current_image = self.current_image.resize((nw, nh), Image.LANCZOS)
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status(f"Resized to {nw}x{nh}.")
        except Exception as e:
            messagebox.showerror("Resize error", f"Failed to resize image:\n{e}")

    def undo(self):
        if self._undo_image is None:
            messagebox.showinfo("Undo", "Nothing to undo.")
            return
        tmp = self.current_image
        self.current_image = self._undo_image
        self._undo_image = tmp
        self.fit_to_window()
        self.display_image()
        self._update_thumbnails()
        self.set_status("Undo performed.")

    def reset_image(self):
        if self.original_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return
        self._store_undo()
        self.current_image = self.original_image.copy()
        self.reset_adjustments()
        self.fit_to_window()
        self.display_image()
        self._update_thumbnails()
        self.set_status("Reset to original image.")

    # -------------------------
    # Crop tool handlers
    # -------------------------
    def toggle_crop_mode(self):
        if self.current_image is None:
            messagebox.showinfo("Crop", "Open an image first.")
            return
        self.crop_mode = not self.crop_mode
        if self.crop_mode:
            self.set_status("Crop mode ON — drag on canvas to select area, release to crop.")
        else:
            # cancel any active rect
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.set_status("Crop mode OFF.")
        # ensure current view updated
        self.display_image()

    def _on_canvas_down(self, event):
        if not self.crop_mode or self.current_image is None:
            return
        # start cropping rectangle
        x, y = event.x, event.y
        # only start if inside displayed image bounds
        if not self._point_in_display(x, y):
            return
        self.crop_start = (x, y)
        # create rectangle id
        if self.crop_rect_id:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self.crop_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="red", width=2)

    def _on_canvas_drag(self, event):
        if not self.crop_mode or self.current_image is None or not self.crop_start:
            return
        x0, y0 = self.crop_start
        x1, y1 = event.x, event.y
        # clamp to display bounds
        x1 = max(self.display_offset_x, min(x1, self.display_offset_x + self.display_w))
        y1 = max(self.display_offset_y, min(y1, self.display_offset_y + self.display_h))
        self.canvas.coords(self.crop_rect_id, x0, y0, x1, y1)

    def _on_canvas_up(self, event):
        if not self.crop_mode or self.current_image is None or not self.crop_start:
            return
        x0, y0 = self.crop_start
        x1, y1 = event.x, event.y
        # ensure there is a valid selection
        # clamp to display bounds
        x0c = max(self.display_offset_x, min(x0, self.display_offset_x + self.display_w))
        y0c = max(self.display_offset_y, min(y0, self.display_offset_y + self.display_h))
        x1c = max(self.display_offset_x, min(x1, self.display_offset_x + self.display_w))
        y1c = max(self.display_offset_y, min(y1, self.display_offset_y + self.display_h))
        left = min(x0c, x1c)
        top = min(y0c, y1c)
        right = max(x0c, x1c)
        bottom = max(y0c, y1c)
        # minimal size
        if abs(right - left) < 10 or abs(bottom - top) < 10:
            # cancel selection
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.crop_start = None
            self.set_status("Crop selection too small; cancelled.")
            return

        # map display coords to image coords
        img_left, img_top = self._display_to_image_coords(left, top)
        img_right, img_bottom = self._display_to_image_coords(right, bottom)
        # clamp to image bounds
        w, h = self.current_image.size
        img_left = max(0, min(w, img_left))
        img_top = max(0, min(h, img_top))
        img_right = max(0, min(w, img_right))
        img_bottom = max(0, min(h, img_bottom))

        if img_right - img_left < 2 or img_bottom - img_top < 2:
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.crop_start = None
            self.set_status("Crop selection too small after mapping; cancelled.")
            return

        # perform crop (permanent)
        self._store_undo()
        try:
            self.current_image = self.current_image.crop((img_left, img_top, img_right, img_bottom))
            self.crop_mode = False
            # remove rectangle
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.crop_start = None
            self.fit_to_window()
            self.display_image()
            self._update_thumbnails()
            self.set_status(f"Cropped to {self.current_image.size[0]}x{self.current_image.size[1]}.")
        except Exception as e:
            messagebox.showerror("Crop error", f"Failed to crop image:\n{e}")
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.crop_start = None

    def _point_in_display(self, x, y):
        """Return True if canvas point (x,y) lies inside the currently displayed image area."""
        return (self.display_offset_x <= x <= self.display_offset_x + self.display_w) and (self.display_offset_y <= y <= self.display_offset_y + self.display_h)

    def _display_to_image_coords(self, dx, dy):
        """Convert canvas/display coordinates to image pixel coordinates (integers)."""
        # dx, dy are canvas coords; subtract offset, then divide by display_scale
        rel_x = dx - self.display_offset_x
        rel_y = dy - self.display_offset_y
        if rel_x < 0: rel_x = 0
        if rel_y < 0: rel_y = 0
        img_x = int(round(rel_x / self.display_scale))
        img_y = int(round(rel_y / self.display_scale))
        return img_x, img_y

    # -------------------------
    # End of class
    # -------------------------


def main():
    root = tk.Tk()
    app = ImageEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
