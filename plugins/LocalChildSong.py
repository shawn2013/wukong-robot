# -*- coding: utf-8-*-
import os
import shutil
import string
import random
from robot import config, logging
from robot.sdk.AbstractPlugin import AbstractPlugin

logger = logging.getLogger(__name__)

class ChildSongPlayer(object):

    def __init__(self, playlist, path, plugin):
        super(ChildSongPlayer, self).__init__()
        self.playlist = playlist
        self.plugin = plugin
        self.idx = 0
        self.volume = 1.003
        self.path = path
        
    def reload(self):
        song_list = list(filter(lambda d: d.endswith('.mp3'), os.listdir(self.path)))
        random.shuffle(song_list)
        self.playlist = [os.path.join(self.path, song) for song in song_list]
        logger.debug(self.playlist)

    def play(self):
        logger.debug('ChildSongPlayer play')
        path = self.playlist[self.idx]
        if os.path.exists(path):
            self.plugin.play(path, False, self.next, self.volume)
        else:
            logger.error('文件不存在: {}'.format(path))
        #self.reload()

    def report(self):
        filename = os.path.basename(self.playlist[self.idx])
        return filename.replace('.mp3', '')
        

    def next(self):
        logger.debug('ChildSongPlayer next')
        self.idx = (self.idx+1) % len(self.playlist)
        self.play()

    def prev(self):
        logger.debug('ChildSongPlayer prev')
        self.idx = (self.idx-1) % len(self.playlist)
        self.play()

    def stop(self):
        logger.debug('ChildSongPlayer stop')
  
    def turnUp(self):
        if self.volume < 1.003:
            self.volume += 0.2
        self.play()

    def turnDown(self):
        if self.volume > 0:
            self.volume -= 0.2
        self.play()

    def demand(self, name):
        #logger.info('demand play ' + name)
        #self.reload()
        for i in range(len(self.playlist)):
            filename = os.path.basename(self.playlist[i])
            #logger.info(filename + "," + name)
            if filename.find(name) != -1:
                self.idx = i
                break
            else:
                continue
        self.play()

    def delete(self):
        #logger.debug('delete music file')
        deleted = self.path + "/deleted"
        path = self.playlist[self.idx]
        if os.path.exists(path):
            if not os.path.exists(deleted):
                os.mkdir(deleted)
            shutil.move(path, deleted)
            #self.reload()
        else:
            logger.error('文件不存在: {}'.format(path))

    def move(self, name):
        deleted = self.path + "/deleted"
        if not os.path.exists(deleted):
            os.mkdir(deleted)        
        for i in range(len(self.playlist)):
            filename = os.path.basename(self.playlist[i])
            if filename.find(name) != -1:
                shutil.move(self.playlist[i], deleted)
                return
            else:
                continue


class Plugin(AbstractPlugin):

    IS_IMMERSIVE = True  # 这是个沉浸式技能

    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.player = None
        self.song_list = None

    def get_song_list(self, path):
        if not os.path.exists(path) or \
           not os.path.isdir(path):
            return []
        song_list = list(filter(lambda d: d.endswith('.mp3'), os.listdir(path)))
        random.shuffle(song_list)
        return [os.path.join(path, song) for song in song_list]

    def init_music_player(self):
        path = config.get('/LocalChildSongPlayer/path')
        self.song_list = self.get_song_list(path)
        if self.song_list == None:
            logger.error('{} 插件配置有误'.format(self.SLUG))
        return ChildSongPlayer(self.song_list, path, self)

    def handle(self, text, parsed):
        if not self.player:
            self.player = self.init_music_player()    
        if len(self.song_list) == 0:
            self.clearImmersive()  # 去掉沉浸式
            self.say('本地音乐目录并没有音乐文件，播放失败')
            return
        if self.nlu.hasIntent(parsed, 'MUSICINFO'):
            slots = self.nlu.getSlots(parsed, 'MUSICINFO')
            for slot in slots:
                if slot['name'] == 'user_music_name':                    
                    word = self.nlu.getSlotWords(parsed, 'MUSICINFO', 'user_music_name')[0]
                    if '歌名' in word:
                        name = self.player.report()
                        self.say('当前播放的是' + name)
                        self.player.play()
                        return
                    else:
                        self.say('点播音乐' + word)
                        self.player.demand(word)
                        return
        elif self.nlu.hasIntent(parsed, 'MUSICRANK'):
            logger.debug('MUSICRANK')
            self.player.play()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_NEXT'):
            self.say('下一首歌')
            self.player.next()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_LAST'):
            self.say('上一首歌')
            self.player.prev()
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL'):
            slots = self.nlu.getSlots(parsed, 'CHANGE_VOL')
            for slot in slots:
                if slot['name'] == 'user_d':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_d')[0]
                    if word == '--HIGHER--':
                        self.say('调大音量')
                        self.player.turnUp()
                    else:
                        self.say('调小音量')
                        self.player.turnDown()
                    return
                elif slot['name'] == 'user_vd':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_vd')[0]
                    if word == '--LOUDER--':
                        self.say('大声一点')
                        self.player.turnUp()
                    else:
                        self.say('小声一点')
                        self.player.turnDown()
        elif self.nlu.hasIntent(parsed, 'DELETE'):
            self.player.delete()
            self.say('已为您移除这首歌')
            self.player.play()
        elif self.nlu.hasIntent(parsed, 'MOVE_MUSIC'):
            slots = self.nlu.getSlots(parsed, 'MOVE_MUSIC')
            if slots:                
                for slot in slots:
                    if slot['name'] == 'user_delete_music':
                        word = self.nlu.getSlotWords(parsed, 'MOVE_MUSIC', 'user_delete_music')[0]
                        self.say('移除音乐' + word)
                        self.player.move(word)
                        break
            else:
               self.player.delete()
               self.say('已为您移除这首歌')
            self.player.play()
        elif self.nlu.hasIntent(parsed, 'CLOSE_MUSIC') or self.nlu.hasIntent(parsed, 'PAUSE'):
            self.player.stop()
            self.clearImmersive()  #去掉沉浸式
            self.say('退出播放')
        else:
            self.say('没听懂你的意思呢，要停止播放，请说停止播放')
            self.player.play()

    def restore(self):
        if self.player:
            self.player.play()

    def isValidImmersive(self, text, parsed):		
        return any(self.nlu.hasIntent(parsed, intent) for intent in ['CHANGE_TO_LAST', 'CHANGE_TO_NEXT', 'CHANGE_VOL', 'CLOSE_MUSIC', 'PAUSE', 'MUSICINFO','DELETE','MOVE_MUSIC'])

    def isValid(self, text, parsed):
        #return '放儿歌' in text
        return '儿歌' in text and \
            any(word in text for word in ['唱', '放', '播放', '来一首'])

