from pathlib import Path 

from udemy_dl .models import Course ,DownloadProgress ,Lecture 


class TestCourse :
    def test_from_api_valid (self ):
        course =Course .from_api ({"id":42 ,"title":"Test Course"})
        assert course is not None 
        assert course .id ==42 
        assert course .title =="Test Course"

    def test_from_api_missing_id (self ):
        assert Course .from_api ({"id":None ,"title":"No ID"})is None 

    def test_from_api_empty_title (self ):
        assert Course .from_api ({"id":1 ,"title":""})is None 

    def test_from_api_missing_both (self ):
        assert Course .from_api ({})is None 

    def test_frozen (self ):
        course =Course (id =1 ,title ="Test")
        import pytest 

        with pytest .raises (AttributeError ):
            course .id =2 


class TestLecture :
    def test_has_video_true (self ):
        lec =Lecture (id =1 ,title ="Intro",url ="https://example.com/v.mp4",file_path =Path ("/tmp/v.mp4"))
        assert lec .has_video is True 

    def test_has_video_false (self ):
        lec =Lecture (id =1 ,title ="Intro",url ="",file_path =Path ("/tmp/v.mp4"))
        assert lec .has_video is False 


class TestDownloadProgress :
    def test_overall_percent_zero_total (self ):
        p =DownloadProgress (total_vids =0 ,done_vids =0 )
        assert p .overall_percent ==0.0 

    def test_overall_percent (self ):
        p =DownloadProgress (total_vids =10 ,done_vids =5 )
        assert p .overall_percent ==50.0 

    def test_video_percent_zero_duration (self ):
        p =DownloadProgress (vid_duration_secs =0 ,vid_current_secs =0 )
        assert p .video_percent ==0.0 

    def test_video_percent (self ):
        p =DownloadProgress (vid_duration_secs =100 ,vid_current_secs =25 )
        assert p .video_percent ==25.0 
