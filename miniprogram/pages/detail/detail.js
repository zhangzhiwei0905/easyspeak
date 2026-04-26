/**
 * EasySpeak - Detail Page (推送详情页)
 * Shows full content for a daily push: phrases, words, tips.
 * Receives content_id via page options (id or content_id).
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function formatDisplayDate(dateStr) {
  if (!dateStr) return ''
  var parts = dateStr.split('-')
  return parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日'
}

function formatDateStr(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + d
}

function getWeekday(dateStr) {
 if (!dateStr) return ''
 var d = new Date(dateStr + 'T00:00:00')
 return WEEKDAYS[d.getDay()]
}


Page({
 data: {
 // Content ID
 contentId: null,

 // Loading / error
 loading: true,
 error: false,
 errorMsg: '',

 // Content data
 content: null,
 dateDisplay: '',
 weekday: '',
 themeZh: '',
 themeEn: '',
 category: '',
 categoryZh: '',
 introduction: '',
 practiceTips: '',

    // Phrases (normalized)
    phrases: [],

    // Words (normalized)
    words: [],

    // Active tab for phrases/words section
    activeTab: 'phrases',

    // Expanded phrase index (-1 = none expanded)
    expandedPhraseIndex: -1,

    // Expanded word index (-1 = none expanded)
    expandedWordIndex: -1,

    // Study state
    isToday: false,
    hasStudied: false,
    studying: false,
    phraseStudied: false,
    wordStudied: false,

    // Jump target target
    targetType: null,
    targetId: null
  },

  onLoad: function (options) {
    // Accept id or content_id
    var contentId = options.id || options.content_id
    if (!contentId) {
      this.setData({
        loading: false,
        error: true,
        errorMsg: '缺少内容ID参数'
      })
      return
    }

    // Accept optional tab param to scroll to phrases or words
    var targetType = options.targetType || null
    var targetId = options.targetId || null
    var tab = options.tab || 'phrases'

    if (targetType === 'word') tab = 'words'
    if (targetType === 'phrase') tab = 'phrases'

    this.setData({
      contentId: contentId,
      activeTab: tab,
      targetType: targetType,
      targetId: targetId
    })

    this._loadContent()
  },

  onUnload: function () {
    if (this._audioCtx) {
      try { this._audioCtx.stop() } catch (e) {}
      try { this._audioCtx.destroy() } catch (e) {}
      this._audioCtx = null
    }
  },

  onShareAppMessage: function () {
    var theme = this.data.themeZh || '英语口语学习'
    return {
      title: 'EasySpeak · ' + theme,
      path: '/pages/detail/detail?id=' + this.data.contentId
    }
  },

  // ========================
  // Data Loading
  // ========================

  _loadContent: function () {
    var self = this
    var contentId = this.data.contentId

    // Try cache first
    var cacheKey = storage.KEYS.CONTENT_CACHE_PREFIX + 'detail_' + contentId
    var cached = storage.getCache(cacheKey)
    if (cached) {
      console.log('[Detail] Using cached data for content', contentId)
      self._processContent(cached)
      self.setData({ loading: false })
    }

    self.setData({ loading: true, error: false })

    api.get('/daily/content/' + contentId)
      .then(function (data) {
        console.log('[Detail] API response:', data)
        // Cache for 7 days
        storage.setCache(cacheKey, data, storage.TTL.CONTENT_DETAIL)
        self._processContent(data)
        self.setData({ loading: false })
      })
      .catch(function (err) {
        console.error('[Detail] Fetch failed:', err)
        if (cached) {
          // Already showing cached data, just stop loading
          self.setData({ loading: false })
        } else {
          self.setData({
            loading: false,
            error: true,
            errorMsg: err.message || '加载失败，请重试'
          })
        }
      })
  },

  _processContent: function (data) {
    if (!data) {
      this.setData({ error: true, errorMsg: '内容不存在' })
      return
    }

 var content = data.content || data

 // Normalize phrases
    var phrases = (content.phrases || []).map(function (p, index) {
      return {
        id: p.id,
        phrase: p.phrase || '',
        meaning: p.meaning || '',
        explanation: p.explanation || '',
        examples: [
          { en: p.example_1 || '', cn: p.example_1_cn || '' },
          { en: p.example_2 || '', cn: p.example_2_cn || '' },
          { en: p.example_3 || '', cn: p.example_3_cn || '' }
        ].filter(function (e) { return e.en }),
        source: p.source || '',
        sort_order: p.sort_order || index
      }
    })

    // Sort phrases by sort_order
    phrases.sort(function (a, b) { return a.sort_order - b.sort_order })

    // Normalize words
    var words = (content.words || []).map(function (w, index) {
      return {
        id: w.id,
        word: w.word || '',
        phonetic: w.phonetic || '',
        partOfSpeech: w.part_of_speech || '',
        meaning: w.meaning || '',
        example: w.example || '',
        sort_order: w.sort_order || index
      }
    })

    // Sort words by sort_order
    words.sort(function (a, b) { return a.sort_order - b.sort_order })

    var dateStr = content.date || ''
    var isToday = (dateStr === formatDateStr(new Date()))
    var hasStudied = !!(content.studied || content.has_studied)

 this.setData({
 content: content,
 dateDisplay: formatDisplayDate(dateStr),
 weekday: getWeekday(dateStr),
 themeZh: content.theme_zh || '',
 themeEn: content.theme_en || '',
 category: content.category || '',
 categoryZh: content.category_zh || '',
 introduction: content.introduction || '',
 practiceTips: content.practice_tips || content.practiceTips || '',
 phrases: phrases,
 words: words,
 isToday: isToday,
 hasStudied: hasStudied,
 error: false
 }, function() {
      if (this.data.targetType && this.data.targetId) {
        this._scrollToTarget()
      }
    }.bind(this))
  },

  _scrollToTarget: function() {
    var type = this.data.targetType
    var targetId = this.data.targetId
    if (!type || !targetId) return

    var list = type === 'phrase' ? this.data.phrases : this.data.words
    var index = list.findIndex(function(item) { return String(item.id) === String(targetId) })

    if (index !== -1) {
      if (type === 'phrase') {
        this.setData({ expandedPhraseIndex: index })
      } else {
        this.setData({ expandedWordIndex: index })
      }

      setTimeout(function() {
        wx.pageScrollTo({
          selector: '#' + type + '-' + targetId,
          duration: 300,
          offsetTop: -20
        })
      }, 300)
    }
  },

  // ========================
  // Event Handlers
  // ========================

  onTabChange: function (e) {
    var tab = e.currentTarget.dataset.tab
    if (tab === this.data.activeTab) return
    this.setData({
      activeTab: tab,
      expandedPhraseIndex: -1,
      expandedWordIndex: -1
    })
  },

  onPhraseToggle: function (e) {
    var index = e.currentTarget.dataset.index
    var currentExpanded = this.data.expandedPhraseIndex

    if (currentExpanded === index) {
      this.setData({ expandedPhraseIndex: -1 })
    } else {
      this.setData({ expandedPhraseIndex: index })
    }
  },

  onWordPlay: function (e) {
    var word = e.currentTarget.dataset.word
    var type = e.currentTarget.dataset.type || '2'
    if (!word) return

    if (this._audioCtx) {
      try { this._audioCtx.stop() } catch (e) {}
      try { this._audioCtx.destroy() } catch (e) {}
    }

    var self = this
    var audio = wx.createInnerAudioContext()
    this._audioCtx = audio

    var youdaoUrl = 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(word) + '&type=' + type
    var baiduUrl = 'https://fanyi.baidu.com/gettts?lan=en&text=' + encodeURIComponent(word) + '&spd=2&source=web'
    var triedFallback = false

    audio.src = youdaoUrl
    audio.play()

    audio.onError(function (err) {
      console.error('[Detail] Audio error:', err)
      if (!triedFallback) {
        triedFallback = true
        console.log('[Detail] Trying Baidu TTS fallback for:', word)
        if (self._audioCtx) {
          try { self._audioCtx.stop() } catch (e) {}
          try { self._audioCtx.destroy() } catch (e) {}
        }
        var audio2 = wx.createInnerAudioContext()
        self._audioCtx = audio2
        audio2.src = baiduUrl
        audio2.play()
        audio2.onError(function (err2) {
          console.error('[Detail] Baidu TTS fallback also failed:', err2)
          // Silently fail — no toast
        })
      }
      // Silently fail on second error
    })
  },

  onWordToggle: function (e) {
    var index = e.currentTarget.dataset.index
    if (this.data.expandedWordIndex === index) {
      this.setData({ expandedWordIndex: -1 })
    } else {
      this.setData({ expandedWordIndex: index })
    }
  },

  onWordNavigate: function (e) {
    if (this.data.contentId) {
      wx.navigateTo({
        url: '/pages/word-list/word-list?contentId=' + this.data.contentId
      })
    }
  },

  onStartLearnPhrase: function () {
    if (this._promptLearnDraft('phrase')) return

    if (this.data.phraseStudied) {
      // Already studied, allow re-learning
      wx.showModal({
        title: '再学一次？',
        content: '你已经学过今日短语了，要再学一遍吗？',
        confirmText: '再学一次',
        cancelText: '取消',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/learn-session/learn-session?content_id=' + this.data.contentId + '&learn_type=phrase'
            })
          }
        }.bind(this)
      })
      return
    }
    if (!this.data.contentId) return
    wx.navigateTo({
      url: '/pages/learn-session/learn-session?content_id=' + this.data.contentId + '&learn_type=phrase'
    })
  },

  onStartLearnWord: function () {
    if (this._promptLearnDraft('word')) return

    if (this.data.wordStudied) {
      wx.showModal({
        title: '再学一次？',
        content: '你已经学过今日单词了，要再学一遍吗？',
        confirmText: '再学一次',
        cancelText: '取消',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/learn-session/learn-session?content_id=' + this.data.contentId + '&learn_type=word'
            })
          }
        }.bind(this)
      })
      return
    }
    if (!this.data.contentId) return
    wx.navigateTo({
      url: '/pages/learn-session/learn-session?content_id=' + this.data.contentId + '&learn_type=word'
    })
  },

  _promptLearnDraft: function (learnType) {
    if (!this.data.contentId) return false

    var draft = storage.getLearnDraft(this.data.contentId, learnType)
    if (!draft) return false

    var self = this
    var url = '/pages/learn-session/learn-session?content_id=' + self.data.contentId + '&learn_type=' + learnType
    wx.showActionSheet({
      itemList: ['继续上次学习', '重新开始'],
      success: function (res) {
        if (res.tapIndex === 0) {
          wx.navigateTo({ url: url + '&resume=1' })
        } else if (res.tapIndex === 1) {
          storage.removeLearnDraft(self.data.contentId, learnType)
          wx.navigateTo({ url: url })
        }
      }
    })
    return true
  },

  onRetry: function () {
    this._loadContent()
  },

  onPhraseDetail: function (e) {
    var id = e.currentTarget.dataset.id
    if (id) {
      wx.navigateTo({
        url: '/pages/phrase-detail/phrase-detail?id=' + id
      })
    }
  }
})
