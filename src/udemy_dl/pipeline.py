from __future__ import annotations 

import re 
from pathlib import Path 
from typing import List ,Optional ,Protocol ,Set 

from .api import UdemyAPI 
from .config import Config 
from .dl import VideoDownloader 
from .exceptions import CurriculumFetchError 
from .models import Course ,DownloadProgress ,Lecture 
from .state import AppState ,DownloadState 
from .utils import (
ValidationResult ,
get_logger ,
is_ffprobe_available ,
sanitize_filename ,
time_string_to_seconds ,
validate_video ,
)

logger =get_logger (__name__ )

DURATION_REGEX =re .compile (r"duration:\s*(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
STATS_REGEX =re .compile (r"time=(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")





class ProgressReporter (Protocol ):

    def on_log (self ,message :str )->None :
        ...

    def on_progress (
    self ,
    progress :DownloadProgress ,
    course_index :int ,
    total_courses :int ,
    )->None :
        ...

    def is_interrupted (self )->bool :
        ...





class DownloadPipeline :

    def __init__ (
    self ,
    config :Config ,
    api :UdemyAPI ,
    downloader :VideoDownloader ,
    state :AppState ,
    reporter :ProgressReporter ,
    )->None :
        self .config =config 
        self .api =api 
        self .downloader =downloader 
        self .state =state 
        self .reporter =reporter 

    def download_courses (self ,courses :List [Course ])->bool :
        for i ,course in enumerate (courses ,1 ):
            self ._download_course (course ,i ,len (courses ))
            if self .reporter .is_interrupted ():
                self .state .save_state ()
                return False 

        self .state .clear_state ()
        return True 

    def _download_course (self ,course :Course ,index :int ,total :int )->None :
        self .state .current_course_state =DownloadState (
        course_id =course .id ,
        course_title =course .title ,
        total_lectures =0 ,
        )

        progress =DownloadProgress (course_title =course .title )

        try :
            download_queue =self ._build_download_queue (course ,progress )
        except CurriculumFetchError as e :
            self .reporter .on_log (f"[ERROR] {e }")
            self .reporter .on_progress (progress ,index ,total )
            return 

        saved_state =self .state .load_state ()
        completed_lectures :Set [int ]=set ()
        if saved_state and saved_state .course_id ==course .id :
            completed_lectures =set (saved_state .completed_lectures )
            self .reporter .on_log (
            f"[RESUME] Found {len (completed_lectures )} previously completed lectures"
            )

        for lecture in download_queue :
            if self .reporter .is_interrupted ():
                self .reporter .on_log ("[WARN] Download interrupted. Saving progress...")
                self .state .save_state ()
                break 
            self ._download_lecture (
            lecture ,course ,progress ,index ,total ,completed_lectures 
            )

    def _build_download_queue (
    self ,course :Course ,progress :DownloadProgress 
    )->List [Lecture ]:
        curriculum =self .api .get_course_curriculum (course .id )
        download_queue :List [Lecture ]=[]
        chapter_index =0 
        lecture_index =0 
        current_chapter_dir :Optional [Path ]=None 
        base_dir =Path (self .config .dl_path )/sanitize_filename (course .title )

        for item in curriculum :
            item_type =item .get ("_class")
            clean_title =sanitize_filename (str (item .get ("title")or "Unknown"))

            if item_type =="chapter":
                chapter_index +=1 
                lecture_index =0 
                current_chapter_dir =base_dir /f"{chapter_index :02d} - {clean_title }"
            elif item_type =="lecture":
                lecture_index +=1 
                lecture_id =item .get ("id")
                asset =item .get ("asset")
                url =self .downloader .get_quality_video_url (asset )if asset else ""
                if not current_chapter_dir :
                    current_chapter_dir =base_dir /"00 - Uncategorized"
                file_path =(
                current_chapter_dir /f"{lecture_index :03d} - {clean_title }.mp4"
                )
                download_queue .append (
                Lecture (
                id =lecture_id ,
                title =clean_title ,
                url =url ,
                file_path =file_path ,
                )
                )
                progress .total_vids +=1 
                if self .state .current_course_state :
                    self .state .current_course_state .total_lectures +=1 

        return download_queue 

    def _download_lecture (
    self ,
    lecture :Lecture ,
    course :Course ,
    progress :DownloadProgress ,
    course_index :int ,
    total_courses :int ,
    completed_lectures :Set [int ],
    )->None :
        progress .current_file =lecture .title 
        self .reporter .on_progress (progress ,course_index ,total_courses )

        out_path =lecture .file_path 
        out_path .parent .mkdir (parents =True ,exist_ok =True )

        def download_extras ()->None :
            if self .config .download_subtitles and lecture .id :
                subs =self .downloader .download_subtitles (
                course .id ,lecture .id ,out_path 
                )
                if subs :
                    self .reporter .on_log (
                    f"[SUBS] Downloaded {len (subs )} subtitle track(s)"
                    )
            if self .config .download_materials and lecture .id :
                mats =self .downloader .download_materials (
                course .id ,
                lecture .id ,
                out_path ,
                self .reporter .is_interrupted ,
                )
                if mats :
                    self .reporter .on_log (
                    f"[MATS] Downloaded {len (mats )} material file(s)"
                    )

        if lecture .id and lecture .id in completed_lectures :
            self .reporter .on_log (
            f"[CACHE] Skipping completed lecture: {lecture .title [:30 ]}..."
            )
            progress .done_vids +=1 
            if self .state .current_course_state :
                self .state .current_course_state .mark_completed (lecture .id )
            download_extras ()
            return 

        if not lecture .has_video :
            self .reporter .on_log (
            f"[INFO] No video for: {lecture .title [:30 ]}..."
            )
            progress .done_vids +=1 
            if lecture .id and self .state .current_course_state :
                self .state .current_course_state .mark_completed (lecture .id )
                self .state .save_state ()
            download_extras ()
            return 

        if out_path .exists ()and out_path .stat ().st_size >1024 :
            validity =validate_video (out_path )
            if validity in (ValidationResult .VALID ,ValidationResult .UNKNOWN ):
                size_mb =out_path .stat ().st_size /(1024 *1024 )
                self .reporter .on_log (
                f"[CACHE] Skipping existing file: "
                f"{lecture .title [:20 ]}... ({size_mb :.1f}MB)"
                )
                progress .done_vids +=1 
                if lecture .id and self .state .current_course_state :
                    self .state .current_course_state .mark_completed (lecture .id )
                    self .state .save_state ()
                download_extras ()
                return 
            else :
                self .reporter .on_log (
                f"[WARN] Invalid file detected, re-downloading: "
                f"{lecture .title [:20 ]}"
                )
                out_path .unlink ()
        elif out_path .exists ():
            self .reporter .on_log (
            f"[WARN] Overwriting partial file: {lecture .title [:20 ]}"
            )

        self .reporter .on_log (f"[DOWNLOAD] Starting: {lecture .title [:30 ]}...")
        proc =self .downloader .download_video (lecture .url ,out_path )

        progress .vid_duration_secs =0 
        progress .vid_current_secs =0 

        try :
            for line in self .downloader .read_ffmpeg_output (proc ):
                if self .reporter .is_interrupted ():
                    proc .terminate ()
                    self .reporter .on_log ("[WARN] FFmpeg terminated by user")
                    break 
                if progress .vid_duration_secs ==0 :
                    if match :=DURATION_REGEX .search (line ):
                        time_val =match .group ("time").split (".")[0 ]
                        progress .vid_duration_secs =time_string_to_seconds (time_val )
                if match :=STATS_REGEX .search (line ):
                    time_val =match .group ("time").split (".")[0 ]
                    progress .vid_current_secs =min (
                    time_string_to_seconds (time_val ),
                    progress .vid_duration_secs ,
                    )
                self .reporter .on_progress (progress ,course_index ,total_courses )
        except (OSError ,ValueError )as e :
            logger .error (f"Error reading ffmpeg output: {e }")

        returncode =self .downloader .wait_for_download (proc )

        if self .reporter .is_interrupted ():
            return 

        validity =validate_video (out_path )
        is_valid =validity in (ValidationResult .VALID ,ValidationResult .UNKNOWN )
        if returncode !=0 :
            self .reporter .on_log (f"[WARN] FFmpeg exited with code {returncode }")
            if not is_ffprobe_available ():
                is_valid =False 

        if out_path .exists ()and is_valid :
            progress .done_vids +=1 
            self .reporter .on_log (f"[DONE] Finished: {lecture .title [:30 ]}")
            if lecture .id and self .state .current_course_state :
                self .state .current_course_state .mark_completed (lecture .id )
                self .state .save_state ()
            download_extras ()
        else :
            self .reporter .on_log (
            f"[ERROR] Download failed or invalid file: {lecture .title [:30 ]}"
            )
            if out_path .exists ():
                out_path .unlink ()
