from collections import OrderedDict
from datetime import datetime
from hashlib import sha1

from flask import request
from flask_login import AnonymousUserMixin, UserMixin, current_user
from peewee import (BigIntegerField, BooleanField, DateTimeField,
                    ForeignKeyField, IntegerField, TextField)
from peewee import JOIN, Proxy, Model, fn

from core import app_config
from core.helpers import make_raw_request_line

from .permission import Permission


database_proxy = Proxy()


def _get_user():
    return current_user.get_id()


class _Model(Model):
    @classmethod
    def exist(cls, where_clause):
        return cls.select().where(where_clause).exists() > 0

    class Meta:
        database = database_proxy
        only_save_dirty = True


# Database Model
class User(_Model, UserMixin):
    id = TextField(primary_key=True)
    name = TextField(unique=True, null=False)
    password = TextField(null=False)
    permission = BigIntegerField(default=0)
    expired = BooleanField(default=False)
    last_login = DateTimeField(default=datetime.utcfromtimestamp(0))
    create_time = DateTimeField(default=datetime.utcnow)

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)
        if kargs.get('password') is not None:
            self.set_password(kargs.pop('password'))

    def to_dict(self, with_perimission=False):
        rv = OrderedDict()
        rv['id'] = self.id
        rv['name'] = self.name
        if with_perimission:
            rv['permission'] = Permission.format_permission(self.permission)
        rv['expired'] = self.expired
        rv['last_login'] = self.last_login
        return rv

    def can(self, permission):
        return bool(self.permission & permission)

    def check_password(self, enc_password, timestamp):
        cipher = sha1((self.password + str(timestamp)).encode()).hexdigest()
        return cipher == enc_password

    def set_password(self, plain_password):
        salt = app_config['USER_PASSWORD_SALT']
        raw = (plain_password + salt).encode('utf-8')
        self.password = sha1(raw).hexdigest()

    @property
    def is_active(self):
        return not self.expired


class Category(_Model):
    id = TextField(primary_key=True)
    name = TextField(unique=True)
    create_time = DateTimeField(default=datetime.utcnow)
    create_by = ForeignKeyField(User, default=_get_user, null=True,
                                on_update='CASCADE', on_delete='SET NULL')

    @classmethod
    def query(cls):
        return cls.select(cls, fn.Count(Article.id).alias('count')) \
                  .join(Article, JOIN.LEFT_OUTER) \
                  .switch(cls).group_by(cls)

    def to_dict(self):
        rv_dict = OrderedDict()
        rv_dict['id'] = self.id
        rv_dict['name'] = self.name

        if hasattr(self, 'count'):
            rv_dict['article_count'] = self.count
        return rv_dict


class Article(_Model):
    id = TextField(primary_key=True)

    is_commentable = BooleanField(default=True)
    title = TextField()
    text_type = TextField()
    source_text = TextField()
    content = TextField(null=True)
    read_count = IntegerField(default=0)
    post_time = DateTimeField(default=datetime.utcnow)
    update_time = DateTimeField(default=datetime.utcnow)
    public = BooleanField(default=True)

    category = ForeignKeyField(Category, null=True,
                               on_update='CASCADE', on_delete='SET NULL',
                               related_name='articles')
    author = ForeignKeyField(User, default=_get_user, null=True,
                             on_delete='SET NULL', on_update='CASCADE',
                             related_name='articles')

    @classmethod
    def query(cls):
        query = cls.select(Article, Category, User) \
                   .join(Category, JOIN.LEFT_OUTER) \
                   .join(User, JOIN.LEFT_OUTER)
        return query

    def to_dict(self, with_content=False, with_src=False):
        rv_dict = OrderedDict()
        rv_dict['id'] = self.id
        rv_dict['title'] = self.title
        if self.author:
            rv_dict['author'] = OrderedDict()
            rv_dict['author']['id'] = self.author.id
            rv_dict['author']['name'] = self.author.name
        if self.category:
            rv_dict['category'] = OrderedDict()
            rv_dict['category']['id'] = self.category.id
            rv_dict['category']['name'] = self.category.name
        if with_content:
            rv_dict['content'] = self.content
        rv_dict['public'] = self.public
        rv_dict['is_commentable'] = self.is_commentable
        rv_dict['read_count'] = self.read_count
        rv_dict['post_time'] = self.post_time
        rv_dict['update_time'] = self.update_time
        if with_src:
            rv_dict['text_type'] = self.text_type
            rv_dict['source_text'] = self.source_text
        return rv_dict


class Comment(_Model):
    content = TextField()
    nickname = TextField()
    reviewed = BooleanField(default=False)
    is_author = BooleanField(default=False)
    create_time = DateTimeField(default=datetime.utcnow)
    ip_address = TextField(default=lambda: request.remote_addr, null=True)

    user = ForeignKeyField(User, default=_get_user, null=True,
                           on_update='CASCADE', on_delete='CASCADE')
    article = ForeignKeyField(Article,
                              on_update='CASCADE', on_delete='CASCADE')
    reply_to = ForeignKeyField('self', null=True,
                               on_delete='SET NULL', on_update='CASCADE')

    def __repr__(self):
        return '<Comment id=%d, parent_id=%s>' % (self.id, self.parent_id)

    @property
    def display_name(self):
        return '[Author]' + self.user.name if self.is_author else self.nickname

    def to_dict(self):
        rv_dict = OrderedDict()
        rv_dict['id'] = self.id
        rv_dict['content'] = self.content
        rv_dict['nickname'] = self.nickname
        if self.is_author:
            rv_dict['is_author'] = self.is_author
        rv_dict['create_time'] = self.create_time
        rv_dict['reply_to'] = self.reply_to_id
        return rv_dict


class Event(_Model):
    type = TextField()
    description = TextField()
    ip_address = TextField(default=lambda: request.remote_addr, null=True)
    endpoint = TextField(default=lambda: request.endpoint)
    request = TextField(default=make_raw_request_line)
    create_time = DateTimeField(default=datetime.utcnow)

    user = ForeignKeyField(User, default=_get_user, null=True,
                           on_update='CASCADE', on_delete='CASCADE')


# For :ref:`flask_login`
class AnonymousUser(AnonymousUserMixin):
    permission = None

    def can(self, permission):
        pass


User._meta.db_table = 'users'
tables = [User, Category, Article, Comment, Event]
