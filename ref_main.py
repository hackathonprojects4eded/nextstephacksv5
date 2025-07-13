import platform
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import PIL.Image, PIL.ImageTk
from PIL import Image, ImageTk
import os
import threading
import tkintermapview

import cv2

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


from video import MyVideoCapture
from audio import AudioRecorder, dB_to_amplitude
from aiaudio import GPTConverter, MyAITalking
from character import MyCharacter

if platform.system() == "Darwin":
    threshold_dB = -25
else:
    threshold_dB = -40
threshold_talking_dB = 20
threshold_amplitude = dB_to_amplitude(threshold_dB)


class App:
    def __init__(self, window, window_title, video_source=0):
        self.window = window
        self.window.title(window_title)
        self.video_source = video_source
        self.vid = None
        self.recorder = None
        self.recording_thread = None
        self.gpt_converter = GPTConverter()
        self.transcribed_text = ""
        self.doctor = MyCharacter()
        self.avatar_talking = None  # Add this for MyAITalking
        self.snapshot_count = 0  # Counter for the number of snapshots taken
        self.max_snapshots = 2  # Maximum allowed snapshots per session
        self.mental_health_index_list = []
        self.toggle_convo_hist = False
        self.toggle_map = False

        self.title_label = tk.Label(window, text="Calls4Mental", font=("Arial", 24))
        self.title_label.pack(side=tk.TOP, pady=10)

        # self.btn_switchmodes = tk.Button(
        #     window, text="Talk to yourself", command=self.switchmodes
        # )
        # self.btn_switchmodes.pack(side=tk.BOTTOM, pady=5)
        self.summaries_frame = tk.Frame(window, width=600, height=600)
        self.map_frame = tk.Frame(window, width=600, height=600)

        self.left_frame = tk.Frame(window, width=500, height=600)
        self.left_frame.pack(side=tk.LEFT, padx=10, pady=10)

        self.right_frame = tk.Frame(window)
        self.soundbar_frame = tk.Frame(window)

        self.characters = {
            "Ket": {
                "idle": "assets/characters/Ket/idle.png",
                "active": "assets/characters/Ket/active.png",
                "think": "assets/characters/Ket/think.png",
            },
            "Chub": {
                "idle": "assets/characters/Chub/idle.png",
                "active": "assets/characters/Chub/active.png",
                "think": "assets/characters/Chub/think.png",
            },
            "Gojo": {
                "idle": "assets/characters/Gojo/idle.png",
                "active": "assets/characters/Gojo/active.png",
                "think": "assets/characters/Gojo/think.png",
            },
            "Ryuji": {
                "idle": "assets/characters/Ryuji/idle.png",
                "active": "assets/characters/Ryuji/active.png",
                "think": "assets/characters/Ryuji/think.png",
            },
            "Rem": {
                "idle": "assets/characters/Rem/idle.png",
                "active": "assets/characters/Rem/active.png",
                "think": "assets/characters/Rem/think.png",
            },
        }
        self.voices = ["alloy", "echo", "shimmer"]

        self.therapist_data = [
            {"email": "eddietang2314@gmail.com", "name": "Eddie Tang"},
        ]

        self.summaries_list_frame = tk.Frame(self.summaries_frame)
        self.summaries_scrollbar = tk.Scrollbar(self.summaries_list_frame)
        self.summaries_listbox = tk.Listbox(
            self.summaries_list_frame,
            yscrollcommand=self.summaries_scrollbar.set,
            height=7,
            width=50,
            justify="center",
        )
        self.summaries_listbox.bind("<ButtonRelease-1>", self.show_item_details)
        self.summaries_listbox.bind(
            "<FocusOut>", lambda e: self.summaries_listbox.selection_clear(0, tk.END)
        )
        self.summaries_scrollbar.config(command=self.summaries_listbox.yview)

        self.summaries_list_frame.pack(side=tk.TOP, pady=10)
        self.summaries_listbox.pack(side=tk.LEFT, padx=5)
        self.summaries_scrollbar.pack(side="right", fill="y")

        self.plot_frame = tk.Frame(self.summaries_frame)
        self.plot_frame.pack(side=tk.BOTTOM, pady=5)

        self.dropdown_frame = tk.Frame(self.left_frame)
        self.dropdown_frame.pack(pady=10)

        self.selected_character = tk.StringVar(value="Ket")
        self.dropdown = ttk.Combobox(
            self.dropdown_frame,
            textvariable=self.selected_character,
            values=list(self.characters.keys()),
            state="readonly",
        )
        self.dropdown.pack(padx=5, side=tk.LEFT)
        self.dropdown.bind("<<ComboboxSelected>>", self.change_character)

        self.selected_voice = tk.StringVar(value="alloy")
        self.voice_dropdown = ttk.Combobox(
            self.dropdown_frame,
            textvariable=self.selected_voice,
            values=self.voices,
            state="readonly",
        )
        self.voice_dropdown.pack(padx=5, side=tk.LEFT)

        self.window.bind("<Button-1>", self.unfocus)

        self.avatar_canvas = tk.Canvas(self.left_frame, width=500, height=600)
        self.avatar_canvas.pack()

        # Camera area
        self.camera_canvas = tk.Canvas(self.right_frame, width=600, height=500)

        self.camera_buttons_frame = tk.Frame(self.left_frame)
        self.camera_buttons_frame.pack(pady=10)

        self.btn_open_camera = tk.Button(
            self.camera_buttons_frame, text="Open Camera", command=self.open_camera
        )
        self.btn_open_camera.pack(side=tk.LEFT, padx=5)

        self.btn_close_camera = tk.Button(
            self.camera_buttons_frame,
            text="Close Camera",
            command=self.close_camera,
            state=tk.DISABLED,
        )
        self.btn_close_camera.pack(side=tk.LEFT, padx=5)

        self.call_buttons_frame = tk.Frame(self.left_frame)
        self.call_buttons_frame.pack(pady=5)

        call = ImageTk.PhotoImage(Image.open("assets/call.png").resize((50, 50)))
        endcall = ImageTk.PhotoImage(Image.open("assets/endcall.png").resize((50, 50)))
        self.start_call_button = tk.Button(
            self.call_buttons_frame,
            text=f"Start a call with {self.selected_character.get()}",
            image=call,
            command=self.start_call,
        )
        self.start_call_button.pack(side=tk.LEFT, padx=5)

        self.end_call_button = tk.Button(
            self.call_buttons_frame,
            text="End Call",
            image=endcall,
            command=self.end_call,
            state=tk.DISABLED,
        )
        self.end_call_button.pack(side=tk.LEFT, padx=5)

        self.more_actions_frame = tk.Frame(self.left_frame)
        self.more_actions_frame.pack(pady=5)

        self.view_history = tk.Button(
            self.more_actions_frame,
            text="Toggle Conversation History",
            command=self.toggle_convo_hist_function,
        )
        self.view_history.pack(side=tk.LEFT, padx=5)

        self.neighbors_button = tk.Button(
            self.more_actions_frame,
            text="Toggle Neighboring Users Map",
            command=self.toggle_map_function,
        )
        self.neighbors_button.pack(side=tk.LEFT, padx=5)

        # Sound meter hidden by default
        self.sound_meter_frame = tk.Frame(self.soundbar_frame)
        self.sound_meter_label = tk.Label(
            self.sound_meter_frame, text="Your 🎙️", font=("Arial", 14)
        )
        self.sound_meter_label.pack()

        self.sound_meter_canvas = tk.Canvas(
            self.sound_meter_frame, width=40, height=100, bg="white"
        )
        self.sound_meter_canvas.pack()

        self.sound_meter_frame.pack_forget()  # Hide the sound meter initially

        self.delay = 15
        self.update_avatar()

        self.window.bind("<Escape>", lambda e: self.close_win(e))
        self.window.mainloop()

    def unfocus(self, event):
        try:
            if self.dropdown.focus_get() == self.dropdown:
                self.window.focus()
            elif self.voice_dropdown.focus_get() == self.voice_dropdown:
                self.window.focus()
        except:
            # root.after(100, show_focus), if this statement put here, this function will stop if no exception
            pass
        # self.window.after(100, self.unfocus_combobox)

    def update_avatar(self, thinking: str = "cope", state=True):
        character = self.selected_character.get()
        image_path = self.characters[character]["idle"]

        if thinking != "cope" and state:
            image_path = self.characters[character]["think"]

        if os.path.exists(image_path):
            self.avatar_image = PIL.Image.open(image_path)
            self.avatar_photo = PIL.ImageTk.PhotoImage(self.avatar_image)
            self.avatar_canvas.delete("all")
            self.avatar_canvas.create_image(0, 0, image=self.avatar_photo, anchor=tk.NW)

        self.start_call_button.config(text=f"Start a call with avatar: {character}")

    def change_character(self, event):
        self.update_avatar()
        if self.avatar_talking:
            self.avatar_talking.character_name = self.selected_character.get()

    def open_camera(self):
        if self.vid is None:
            if self.toggle_convo_hist:
                self.toggle_convo_hist_function()
            self.vid = MyVideoCapture(self.video_source)
            # self.camera_canvas.config(width=self.vid.width, height=self.vid.height)
            self.btn_open_camera.config(state=tk.DISABLED)
            self.btn_close_camera.config(state=tk.NORMAL)

            # Expand the window and reposition elements
            self.right_frame.pack(side=tk.LEFT, padx=10)
            self.soundbar_frame.pack(side=tk.LEFT, padx=10)
            self.camera_canvas.pack()
            self.sound_meter_frame.pack(pady=10)  # Show the sound meter

            self.update_camera()

    def close_camera(self):
        if self.vid is not None:
            self.vid = None  # Simulate closing the camera
            self.camera_canvas.delete(
                "all"
            )  # Clear the canvas when the camera is closed
            # Enable the "Open Camera" button and disable "Close Camera"
            self.btn_open_camera.config(state=tk.NORMAL)
            self.btn_close_camera.config(state=tk.DISABLED)

            # Hide the camera and sound meter, move action buttons under the avatar
            self.right_frame.pack_forget()
            self.soundbar_frame.pack_forget()
            self.camera_canvas.pack_forget()
            self.sound_meter_frame.pack_forget()
            self.call_buttons_frame.pack(pady=10)
            self.camera_buttons_frame.pack(pady=10)

    def update_camera(self):
        if self.vid is not None:
            ret, frame = self.vid.get_frame()
            if ret:
                self.photo = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(frame))
                self.camera_canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
            self.window.after(self.delay, self.update_camera)

    def get_camera_snapshot(self):
        """Take a snapshot and save it if the limit is not reached"""
        if self.snapshot_count >= self.max_snapshots:
            print(
                f"Snapshot limit reached. Only {self.max_snapshots} allowed per session."
            )
            return False, ""

        if self.vid is not None:
            ret, frame = self.vid.get_frame()
            if ret:
                os.chdir("conversations")
                cv2.imwrite("frame.jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                os.chdir("..")
                self.snapshot_count += 1  # Increment snapshot count
                print(f"Snapshot taken. Total snapshots: {self.snapshot_count}")
                return True, "conversations/frame.jpg"
            else:
                return False, ""
        return False, ""

    def reset_session(self):
        """Reset snapshot count for a new session if needed"""
        self.snapshot_count = 0

    def update_sound_meter(self, level):
        self.sound_meter_canvas.delete("all")
        max_height = 100
        bar_height = int(level * max_height)
        self.sound_meter_canvas.create_rectangle(
            10, max_height - bar_height, 30, max_height, fill="green", outline="black"
        )

    def start_call(self):
        if self.recorder is None:
            self.open_camera()
            self.recorder = AudioRecorder(
                threshold_amplitude,
                stop_callback=self.post_process_for_call_message,
            )
            self.recording_thread = threading.Thread(
                target=self.recorder.start_recording
            )
            self.recording_thread.start()
            self.recorder.update_callback = self.update_sound_meter

            self.start_call_button.config(state=tk.DISABLED)
            self.end_call_button.config(state=tk.NORMAL)

        print("Call started.")

    def post_process_for_call_message(self):
        """Process audio file when recording stops"""
        audio_file_path = "conversations/user_input.mp3"
        self.recorder.isAiTalking = True
        print("Processing audio...")
        self.update_avatar(thinking="copium", state=True)

        self.transcribed_text = self.gpt_converter.audio_to_text(audio_file_path)
        print(f"Transcribed text: {self.transcribed_text}")

        _, path = self.get_camera_snapshot()

        response = self.doctor.prompt(self.transcribed_text, path)

        # if platform.system() != "Darwin":
        #     analysis = self.doctor.emotion_and_sentiment_from_text(
        #         self.transcribed_text
        #     )
        #     score = self.doctor.mental_illness_index(analysis)
        #     self.mental_health_index_list.append(score)
        #     print(self.mental_health_index_list)
        #     if score <= -1:
        #         self.doctor.process_index_and_email(
        #             score,
        #             self.therapist_data[0]["email"],
        #             self.therapist_data[0]["name"],
        #         )

        selected_voice = self.selected_voice.get()
        self.gpt_converter.text_to_speech(
            response, "conversations/ai.mp3", selected_voice
        )

        self.update_avatar(thinking="copium", state=False)

        # Initialize MyAITalking and start playback
        self.avatar_talking = MyAITalking(
            self.avatar_canvas,
            self.selected_character.get(),
            threshold=threshold_talking_dB,
        )
       
        self.avatar_talking.play_audio("conversations/ai.mp3")
        while self.avatar_talking.is_playing:
            pass
        self.recorder.isAiTalking = False

    def end_call(self):
        """End the call"""
        if self.recorder is not None:
            self.recorder.stop_recording()
            self.recorder = None
            self.recording_thread = None
            self.reset_session()
            self.close_camera()
            # Stop avatar talking
            if hasattr(self, "avatar_talking"):
                if self.avatar_talking:
                    self.avatar_talking.stop_playing()
                self.update_avatar()

            self.doctor.summarize_conversation(self.mental_health_index_list)
            self.mental_health_index_list = []
            if os.path.exists("conversations/log.json"):
                os.remove("conversations/log.json")
            # Enable start call button and disable end call button
            self.start_call_button.config(state=tk.NORMAL)
            self.end_call_button.config(state=tk.DISABLED)

        print("Call ended.")

    def toggle_map_function(self):
        if not self.toggle_map:
            self.map_widget = tkintermapview.TkinterMapView(
                self.map_frame, width=600, height=600
            )
            self.map_widget.set_position(40.3, -74.3)

            # we can probabbly display therapist locations w this
            marker_1 = self.map_widget.set_marker(40.3, -74.3, text="You")
            marker_2 = self.map_widget.set_marker(
                40.301323, -74.2973, text="Lauren Gembry | 267-833-2606"
            )
            marker_3 = self.map_widget.set_marker(
                40.30198, -74.301123, text="Phil Lane | 908-883-3496"
            )

            self.map_widget.set_zoom(15)
            self.map_widget.pack()

            self.map_frame.pack(side=tk.RIGHT, pady=10, padx=10)
        else:
            self.map_widget.pack_forget()

            self.map_frame.pack_forget()

        # Toggle the map state
        self.toggle_map = not self.toggle_map

    def toggle_convo_hist_function(self):
        if not self.toggle_convo_hist:
            self.summaries_frame.pack(side=tk.RIGHT, pady=10, padx=10)
            self.plot_mental_health_index()

            summaries = self.doctor.load_summaries()
            self.summaries_listbox.delete(0, tk.END)  # Clear the Listbox
            for index, summary in enumerate(summaries, 1):
                self.summaries_listbox.insert(
                    tk.END, f"Conversation {index} | {summary['time']}"
                )

        else:
            self.summaries_frame.pack_forget()

        self.toggle_convo_hist = not self.toggle_convo_hist

        return

    def show_item_details(self, event):
        try:
            # Get the selected item index
            index = self.summaries_listbox.curselection()[0]
            # Load the summaries from file or use the stored summaries
            summaries = self.doctor.load_summaries()
            selected_summary = summaries[index]

            # Create a string with the summary details
            details = (
                f"Conversation {index + 1}\n"
                f"Time: {selected_summary['time']}\n"
                f"Summary: {selected_summary['summary']}\n\n"
                f"Mental Health Index: {selected_summary.get('average_mental_health_index', 'N/A')}"
            )

            # Show the details in a dialog
            messagebox.showinfo("Summary Details", details)
        except IndexError:
            pass
            # messagebox.showwarning(
            #     "Selection Error", "Please select a valid conversation."
            # )

    def plot_mental_health_index(self):
        summaries = self.doctor.load_summaries()
        mental_health_index_list = []
        for summary in summaries:
            mental_health_index_list.append(summary["average_mental_health_index"])

        conversation_numbers = list(range(1, len(mental_health_index_list) + 1))
        plt.figure(figsize=(4, 3.7))
        plt.title("Mental health index v.s\nConversation number")

        # Scatter plot for the points
        plt.scatter(conversation_numbers, mental_health_index_list, color="blue")

        # Line plot to connect the points
        plt.plot(
            conversation_numbers,
            mental_health_index_list,
            color="blue",
            linestyle="-",
            linewidth=1,
        )

        plt.grid(True)

        # Clear the previous plot if it exists
        for widget in self.plot_frame.winfo_children():
            widget.destroy()

        # Create and display the plot
        figure = plt.gcf()
        canvas = FigureCanvasTkAgg(figure, self.plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()

    def close_win(self, e):
        self.end_call()
        self.window.destroy()
