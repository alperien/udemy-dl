from __future__ import annotations 

from dataclasses import dataclass ,field 
from pathlib import Path 
from typing import Any ,Dict ,Optional 


@dataclass (frozen =True )
class Course :

    id :int 
    title :str 

    @classmethod 
    def from_api (cls ,data :Dict [str ,Any ])->Optional ["Course"]:
        course_id =data .get ("id")
        title =data .get ("title")
        if course_id and title :
            return cls (id =int (course_id ),title =str (title ))
        return None 


@dataclass (frozen =True )
class Lecture :

    id :Optional [int ]
    title :str 
    url :str 
    file_path :Path 

    @property 
    def has_video (self )->bool :
        return bool (self .url )


@dataclass 
class DownloadProgress :

    course_title :str =""
    total_vids :int =0 
    done_vids :int =0 
    current_file :str ="Initializing..."
    vid_duration_secs :int =0 
    vid_current_secs :int =0 

    @property 
    def overall_percent (self )->float :
        if self .total_vids <=0 :
            return 0.0 
        return self .done_vids /self .total_vids *100 

    @property 
    def video_percent (self )->float :
        if self .vid_duration_secs <=0 :
            return 0.0 
        return self .vid_current_secs /self .vid_duration_secs *100 
