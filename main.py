# This Python file uses the following encoding: utf-8
import sys, os
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from DownloadSingleVideo import Ui_DownloadSingleVideo
import pyperclip
import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal, QUrl, QTimer, Qt, QAbstractTableModel
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from DB import *
from sqlmodel import select, func
import requests
import pandas as pd

def save_comments_to_db(video_id: int, comments_list: list):
    session = Session(engine)

    for c in comments_list:
        comment = Comment(
            comid=int(c["id"]) if c["id"].isdigit() else 0,
            author=c["author"],
            text=c["text"],
            likecount=c["likecount"],
            video_id=video_id
        )
        session.add(comment)
    session.commit()
    print(f"✅ تم حفظ {len(comments_list)} تعليق في قاعدة البيانات.")

def get_comments(video_url: str):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,       # لا يحمل الفيديو نفسه
        'getcomments': True,         # ✅ ضروري لتحميل التعليقات
        'extract_flat': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    
    comments_data = []
    if 'comments' in info:
        for c in info['comments']:
            comments_data.append({
                "id": c.get("id"),
                "author": c.get("author", "Unknown"),
                "text": c.get("text", ""),
                "likecount": c.get("like_count", 0)
            })
    else:
        print("⚠️ لا توجد تعليقات في هذا الفيديو")

    return comments_data

class PandasModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._df = df

    def rowCount(self, parent=None):
        return len(self._df)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                value = self._df.iloc[index.row(), index.column()]
                return str(value)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._df.columns[section])
            elif orientation == Qt.Orientation.Vertical:
                return str(self._df.index[section])
        return None


def download_image_as_bytes(url: str) -> bytes:
    if not url:
        return b""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"❌ فشل تحميل الصورة: {e}")
        return b""

def create_onevideo_from_d(d, thumb, playlist_id=None):
    # نحصل على الصورة كـ bytes
    img_data = download_image_as_bytes(d['thumbnail'])

    # ننشئ الكائن
    video = OneVideo(
        videoid=d['id'],
        title=d['title'],
        desc=d['description'],
        filepath=thumb['filename'],
        img=img_data,
        playlist_id=playlist_id
    )
    return video

def LoadAllSingleVideos():
    if os.path.exists("downloads_temp/videos/"):
        return os.listdir("downloads_temp/videos/")
    else:
        return []

class DownloadThread(QThread):
    progress_changed = pyqtSignal(int)   # signal يرسل النسبة (0-100)
    quality: str = "1080p"

    def __init__(self, url, quality):
        super().__init__()
        self.url = url
        self.quality = quality
        self.ydl_opts = {
            # ✅ إعدادات التحميل العامة
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': 'videos/%(title)s.%(ext)s',
            'noplaylist': False,
            'ignoreerrors': True,           # تجاهل الفيديوهات المعطوبة
            'continuedl': True,             # استئناف التحميل لو كان ناقص
            'retries': 10,                  # عدد المحاولات عند الفشل
            'fragment_retries': 10,         # محاولات لكل fragment
            'skip_unavailable_fragments': True,
            'keep_fragments': True,         # يحتفظ بالملفات المؤقتة ليستأنف منها
            'file_access_retries': 5,       # إعادة محاولة الكتابة على القرص
            'noprogress': False,
            'concurrent_fragment_downloads': 5,  # تحميل أجزاء متعددة لتسريع السرعة
            'socket_timeout': 30,                # يمنع timeout السريع
            'writethumbnail': False,
            'writeinfojson': True,               # يحفظ JSON بكل بيانات الفيديو
            'quiet': False,
            'verbose': False,
            # ✅ مجلد مؤقت للتحميل (تُستأنف الملفات منه)
            'paths': {'home': os.path.join(os.getcwd(), "downloads_temp")},
        }

        if self.quality == "144p":
            self.ydl_opts['format'] = '160+140/best'
        elif self.quality == "360p":
            self.ydl_opts['format'] = '18/best'
        elif self.quality == "480p":
            self.ydl_opts['format'] = '135+140/best'
        elif self.quality == "720p":
            self.ydl_opts['format'] = '22/best'
        elif self.quality == "1080p":
            self.ydl_opts['format'] = '137+140/best'
        elif self.quality == "4K":
            self.ydl_opts['format'] = '313+251/best'
        elif self.quality == "صوت فقط (m4a)":
            self.ydl_opts['format'] = '140'
        elif self.quality == "صوت فقط (webm)":
            self.ydl_opts['format'] = '251'
        else:
            self.ydl_opts['format'] = 'bestvideo+bestaudio/best'

    def run(self):
        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    percent = int(downloaded * 100 / total)
                    self.progress_changed.emit(percent)
            elif d['status'] == 'finished':
                
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                onevideo = create_onevideo_from_d(info, d)
                session.add(onevideo)
                session.commit()

                save_comments_to_db(info['id'], get_comments(self.url))

                
                self.progress_changed.emit(100)

        # إعداد خيارات yt_dlp
        self.ydl_opts['progress_hooks'] = [progress_hook]
        self.ydl_opts['continuedl'] = True
        self.ydl_opts['ignoreerrors'] = True
        self.ydl_opts['retries'] = 10
        self.ydl_opts['fragment_retries'] = 10

        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            pass

class DownloadSingleVideo(QMainWindow):
    ThreadOf: DownloadThread

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_DownloadSingleVideo()
        self.ui.setupUi(self)
        self.ui.downloadbtn.clicked.connect(self.DownloadVideo)
        self.ui.pastebtn.clicked.connect(self.PastLink)
        self.ThreadOf = None
        self.ui.Quality.addItems([
            "144p", "360p", "480p", "720p", "1080p", "4K",
            "Voice Only (m4a)", "Voice Only (webm)"
        ])
        self.ui.Quality.setCurrentText("1080p")

        
        # إنشاء المؤقت
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # كل 1000ms = ثانية واحدة

        # ربط المؤقت بدالة (signal-slot)
        self.timer.timeout.connect(self.update_paths)

        # تشغيل المؤقت
        self.timer.start()

        self.timer2 = QTimer(self)
        self.timer2.timeout.connect(self.update_progress)
        self.timer2.start(500)

        self.ui.play_button.clicked.connect(self.toggle_play)

        self.player = None

        self.is_playing = False

        # ⏯️ تشغيل / إيقاف مؤقت
    def toggle_play(self):
        if not self.player:
            return

        if self.is_playing:
            self.player.pause()
            self.ui.play_button.setText("▶️")
        else:
            self.player.play()
            self.ui.play_button.setText("⏸️")
        self.is_playing = not self.is_playing

    # 🔊 تغيير الصوت
    def change_volume(self, value):
        if not self.player:
            return
        
        self.audio_output.setVolume(value / 100)

    # 📈 تحديث شريط التقدم والوقت
    def update_progress(self):
        if not self.player:
            return
        duration = self.player.duration()
        position = self.player.position()
        if duration > 0:
            # progress = int((position / duration) * 1000)

            self.ui.time_label.setText(f"{self.format_time(position)} / {self.format_time(duration)}")

    # ⏩ عند تحريك شريط التقدم
    def seek(self, value):
        if not self.player:
            return
        
        duration = self.player.duration()
        if duration > 0:
            self.player.setPosition(int(duration * (value / 1000)))

    # ⏱️ تحويل الوقت إلى صيغة mm:ss
    def format_time(self, ms):
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"

    
    def selected_changed(self, selected, deselected):
        # لو مافيش صفوف محددة، نخرج
        if not selected.indexes():
            return

        # نأخذ أول صف محدد من المؤشر القادم من الإشارة
        row = selected.indexes()[0].row()

        # نفترض أن الموديل مربوط بـ self.ui.singlevideoshowtable
        model = self.ui.singlevideoshowtable.model()

        # نبحث عن عمود filepath (أو العمود الذي يحوي المسار)
        filepath_column = model.headerData(0, Qt.Orientation.Horizontal)
        filepath_col_index = None
        for i in range(model.columnCount()):
            if model.headerData(i, Qt.Orientation.Horizontal) == "filepath":
                filepath_col_index = i
                break

        if filepath_col_index is None:
            print("⚠️ لم يتم العثور على عمود filepath")
            return

        # نأخذ قيمة المسار من الموديل
        video_path = model.index(row, filepath_col_index).data()

        self.ui.desc.setText(model.index(row, 3).data())
        self.ui.title.setText(model.index(row, 2).data())

        videoid = model.index(row, 1).data()

        self.ui.comments.setModel(PandasModel(pd.read_sql(f"Select author,text,likecount From comment Where video_id = '{videoid}'", engine)))

        self.ui.comments.resizeColumnsToContents()

        if not video_path:
            print("⚠️ لا يوجد مسار فيديو في الصف المحدد")
            return

        # تهيئة المشغل مرة واحدة فقط
        if not self.player:
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)

            self.video_widget = QVideoWidget(self)
            self.player.setVideoOutput(self.video_widget)
            self.ui.playerlayout.addWidget(self.video_widget)

        # تشغيل الفيديو
        print(f"🎬 تشغيل الفيديو: {video_path}")
        self.player.setSource(QUrl.fromLocalFile(video_path))
        self.player.play()

    def update_paths(self):
        countof = session.exec(select(func.count()).select_from(OneVideo)).one()

        if not self.ui.singlevideoshowtable.model():
            self.ui.singlevideoshowtable.setModel(PandasModel(pd.read_sql("Select * From onevideo", engine)))
            self.ui.singlevideoshowtable.selectionModel().selectionChanged.connect(self.selected_changed)

        if countof != self.ui.singlevideoshowtable.model().rowCount():
            self.ui.singlevideoshowtable.setModel(PandasModel(pd.read_sql("Select * From onevideo", engine)))

    def DownloadVideo(self):
        url = self.ui.videourl.text()
        if 'youtube' in url:
            try:
                self.ThreadOf = DownloadThread(url, self.ui.Quality.currentText())
                self.thread = self.ThreadOf
                self.thread.progress_changed.connect(self.ui.ProgressBar.setValue)
                self.thread.start()
            except Exception as ex:
                QMessageBox.information(self, 'Error', f'Insert a valid youtube url: {ex}')  
        else:
            QMessageBox.information(self, 'Error', 'Insert a valid youtube url')

    def PastLink(self):
        pasted = pyperclip.paste()

        if 'youtube' in pasted:
            self.ui.videourl.setText(pyperclip.paste())

if __name__ == "__main__":
    app = QApplication([])
    window = DownloadSingleVideo()
    window.show()
    sys.exit(app.exec())
