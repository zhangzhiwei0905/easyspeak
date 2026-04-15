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

function getWeekday(dateStr) {
  if (!dateStr) return ''
  var d = new Date(dateStr + 'T00:00:00')
  return WEEKDAYS[d.getDay()]
}

function getTimeSlotIcon(timeSlot) {
  return timeSlot === 'evening' ? '🌙' : '☀️'
}

function getTimeSlotLabel(timeSlot) {
  return timeSlot === 'evening' ? '晚间·休闲话题' : '晨间·生活场景'
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
    timeSlot: 'morning',
    timeSlotIcon: '☀️',
    timeSlotLabel: '晨间·生活场景',
    themeZh: '',
    themeEn: '',
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

    // Study state
    hasStudied: false,
    studying: false
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
    var tab = options.tab || 'phrases'

    this.setData({
      contentId: contentId,
      activeTab: tab
    })

    this._loadContent()
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
    var timeSlot = content.time_slot || 'morning'

    // Normalize phrases
    var phrases = (content.phrases || []).map(function (p, index) {
      return {
        id: p.id,
        phrase: p.phrase || '',
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
    var hasStudied = !!(content.studied || content.has_studied)

    this.setData({
      content: content,
      dateDisplay: formatDisplayDate(dateStr),
      weekday: getWeekday(dateStr),
      timeSlot: timeSlot,
      timeSlotIcon: getTimeSlotIcon(timeSlot),
      timeSlotLabel: getTimeSlotLabel(timeSlot),
      themeZh: content.theme_zh || '',
      themeEn: content.theme_en || '',
      introduction: content.introduction || '',
      practiceTips: content.practice_tips || content.practiceTips || '',
      phrases: phrases,
      words: words,
      hasStudied: hasStudied,
      error: false
    })
  },

  // ========================
  // Event Handlers
  // ========================

  onTabChange: function (e) {
    var tab = e.currentTarget.dataset.tab
    if (tab === this.data.activeTab) return
    this.setData({
      activeTab: tab,
      expandedPhraseIndex: -1
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

  onWordTap: function (e) {
    var word = e.currentTarget.dataset.word
    // Navigate to word-list page filtered by this content
    if (this.data.contentId) {
      wx.navigateTo({
        url: '/pages/word-list/word-list?contentId=' + this.data.contentId
      })
    }
  },

  onStartStudy: function () {
    var self = this
    if (self.data.studying || self.data.hasStudied) return
    if (!self.data.contentId) return

    self.setData({ studying: true })

    // Mark content as studied via API
    api.post('/progress/study', {
      content_id: self.data.contentId
    }).then(function (data) {
      // Record study day locally
      storage.recordStudyDay()
      self.setData({
        hasStudied: true,
        studying: false
      })
      wx.showToast({
        title: '打卡成功！继续加油',
        icon: 'success',
        duration: 2000
      })
    }).catch(function (err) {
      console.error('[Detail] Mark study failed:', err)
      // Still mark locally on failure for better UX
      storage.recordStudyDay()
      self.setData({
        hasStudied: true,
        studying: false
      })
      wx.showToast({
        title: '已记录学习',
        icon: 'success',
        duration: 1500
      })
    })
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
