from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel, Column, Unicode, create_engine, Session
import configparser

config = configparser.ConfigParser()
config.read("alembic.ini")
engine = create_engine(config.get("alembic", "sqlalchemy.url"))
session = Session(engine)


class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    comid: int
    author: str = Field(sa_column=Column(Unicode))
    text: str = Field(sa_column=Column(Unicode))
    likecount: int

    video_id: Optional[int] = Field(default=None, foreign_key="onevideo.id")
    video: Optional["OneVideo"] = Relationship(back_populates="comments")


class OneVideo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    videoid: str
    title: str = Field(sa_column=Column(Unicode))
    desc: str = Field(sa_column=Column(Unicode))
    img: bytes
    filepath: str = Field(sa_column=Column(Unicode))

    playlist_id: Optional[int] = Field(default=None, foreign_key="playlistvideos.id")
    playlist: Optional["PlaylistVideos"] = Relationship(back_populates="videos")

    comments: List["Comment"] = Relationship(back_populates="video")


class PlaylistVideos(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    playlistid: str
    title: str = Field(sa_column=Column(Unicode))
    desc: str = Field(sa_column=Column(Unicode))
    img: bytes
    listpath: str = Field(sa_column=Column(Unicode))

    videos: List["OneVideo"] = Relationship(back_populates="playlist")
