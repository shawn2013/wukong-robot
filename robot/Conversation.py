# -*- coding: utf-8-*-
import time 
import uuid
import cProfile
import pstats
import io
import re
from robot.Brain import Brain
from snowboy import snowboydecoder
from robot import logging, ASR, TTS, NLU, AI, Player, config, constants, utils, statistic


logger = logging.getLogger(__name__)

class Conversation(object):

    def __init__(self, profiling=False):
        self.reload()
        # 历史会话消息
        self.history = []
        # 沉浸模式，处于这个模式下，被打断后将自动恢复这个技能
        self.matchPlugin = None
        self.immersiveMode = None
        self.isRecording = False
        self.profiling = profiling
        self.onSay = None
        self.hasPardon = False

    def getHistory(self):
        return self.history

    def interrupt(self):
        if self.player is not None and self.player.is_playing():
            self.player.stop()
            self.player = None
        if self.immersiveMode:
            self.brain.pause()

    def reload(self):
        """ 重新初始化 """
        try:
            self.asr = ASR.get_engine_by_slug(config.get('asr_engine', 'tencent-asr'))
            self.ai = AI.get_robot_by_slug(config.get('robot', 'tuling'))
            self.tts = TTS.get_engine_by_slug(config.get('tts_engine', 'baidu-tts'))
            self.nlu = NLU.get_engine_by_slug(config.get('nlu_engine', 'unit'))
            self.player = None
            self.brain = Brain(self)
            self.brain.printPlugins()
        except Exception as e:
            logger.critical("对话初始化失败：{}".format(e))

    def checkRestore(self):
        if self.immersiveMode:
            self.brain.restore()

    def doResponse(self, query, UUID='', onSay=None):
        statistic.report(1)
        self.interrupt()
        self.appendHistory(0, query, UUID)

        if onSay:
            self.onSay = onSay

        if query is None or query.strip() == '':
            self.pardon()
            return

        lastImmersiveMode = self.immersiveMode

        if not self.brain.query(query):
            # 没命中技能，使用机器人回复
            msg = self.ai.chat(query)
            self.say(msg, True, onCompleted=self.checkRestore)
        else:
            if lastImmersiveMode is not None and lastImmersiveMode != self.matchPlugin:
                time.sleep(1)
                if self.player is not None and self.player.is_playing():
                    logger.debug('等说完再checkRestore')
                    self.player.appendOnCompleted(lambda: self.checkRestore())
                else:
                    logger.debug('checkRestore')
                    self.checkRestore()

    def doParse(self, query, **args):
        return self.nlu.parse(query, **args)

    def setImmersiveMode(self, slug):
        self.immersiveMode = slug

    def getImmersiveMode(self):
        return self.immersiveMode

    def converse(self, fp, callback=None):
        """ 核心对话逻辑 """
        Player.play(constants.getData('beep_lo.wav'))
        logger.info('结束录音')
        self.isRecording = False
        if self.profiling:
            logger.info('性能调试已打开')
            pr = cProfile.Profile()
            pr.enable()
            self.doConverse(fp, callback)
            pr.disable()
            s = io.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            print(s.getvalue())
        else:
            self.doConverse(fp, callback)

    def doConverse(self, fp, callback=None, onSay=None):
        try:
            self.interrupt()
            query = self.asr.transcribe(fp)
            utils.check_and_delete(fp)
            self.doResponse(query, callback, onSay)
        except Exception as e:
            logger.critical(e)
            utils.clean()

    def appendHistory(self, t, text, UUID=''):
        """ 将会话历史加进历史记录 """
        if t in (0, 1) and text is not None and text != '':
            if text.endswith(',') or text.endswith('，'):
                text = text[:-1]
            if UUID == '' or UUID == None or UUID == 'null':
                UUID = str(uuid.uuid1())
            # 将图片处理成HTML
            pattern = r'https?://.+\.(?:png|jpg|jpeg|bmp|gif|JPG|PNG|JPEG|BMP|GIF)'
            url_pattern = r'^https?://.+'
            imgs = re.findall(pattern, text)
            for img in imgs:
                text = text.replace(img, '<img src={} class="img"/>'.format(img))
            urls = re.findall(url_pattern, text)
            for url in urls:
                text = text.replace(url, '<a href={} target="_blank">{}</a>'.format(url, url))
            self.history.append({'type': t, 'text': text, 'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), 'uuid': UUID})

    def _onCompleted(self, msg):
        if config.get('active_mode', False) and \
           (
               msg.endswith('?') or 
               msg.endswith(u'？') or 
               u'告诉我' in msg or u'请回答' in msg
           ):
            query = self.activeListen()
            self.doResponse(query)

    def pardon(self):
        if not self.hasPardon:
            self.say("抱歉，刚刚没听清，能再说一遍吗？", onCompleted=lambda: self.doResponse(self.activeListen()))
            self.hasPardon = True
        else:
            self.say("没听清呢")
            self.hasPardon = False

    def say(self, msg, cache=False, plugin='', onCompleted=None):
        """ 说一句话 """
        if self.onSay:
            logger.info('onSay: {}'.format(msg))
            if plugin != '':
                self.onSay("[{}] {}".format(plugin, msg))
            else:
                self.onSay(msg)
            self.onSay = None
        if plugin != '':
            self.appendHistory(1, "[{}] {}".format(plugin, msg))
        else:
            self.appendHistory(1, msg)
        pattern = r'^https?://.+'
        if re.match(pattern, msg):
            logger.info("内容包含URL，所以不读出来")
            return
        voice = ''
        if utils.getCache(msg):
            logger.info("命中缓存，播放缓存语音")
            voice = utils.getCache(msg)
        else:
            try:
                voice = self.tts.get_speech(msg)
                if cache:
                    utils.saveCache(voice, msg)
            except Exception as e:
                logger.error('保存缓存失败：{}'.format(e))
        if onCompleted is None:
            onCompleted = lambda: self._onCompleted(msg)
        self.player = Player.SoxPlayer()
        self.player.play(voice, not cache, onCompleted)

    def activeListen(self, silent=False):
        """ 主动问一个问题(适用于多轮对话) """
        logger.debug('activeListen')
        try:
            if not silent:
                time.sleep(1)
                Player.play(constants.getData('beep_hi.wav'))
            models = config.get('hotword', 'wukong.pmdl').split(',')
            for i in range(0, len(models)):
                models[i] = constants.getHotwordModel(models[i])
            listener = snowboydecoder.ActiveListener(models)
            #listener = snowboydecoder.ActiveListener([constants.getHotwordModel(config.get('hotword', 'wukong.pmdl'))])
            voice = listener.listen(
                silent_count_threshold=config.get('silent_threshold', 15),
                recording_timeout=config.get('recording_timeout', 5) * 4
            )
            if not silent:
                Player.play(constants.getData('beep_lo.wav'))
            if voice:
                query = self.asr.transcribe(voice)
                utils.check_and_delete(voice)
                return query
            return ''
        except Exception as e:            
            logger.error(e)
            return ''        

    def play(self, src, delete=False, onCompleted=None, volume=1):
        """ 播放一个音频 """
        if self.player:
            self.interrupt()
        self.player = Player.SoxPlayer()
        self.player.play(src, delete, onCompleted=onCompleted, volume=volume)
    
