/**
 * EasySpeak - Phrase Detail Page (短语详情页)
 * Shows full details for a single phrase including explanation,
 * example sentences, source, and mastery rating.
 *
 * Receives phrase_id (as `id`) and optionally content_id via page options.
 * Since there's no dedicated GET /api/v1/phrase/{id} endpoint,
 * we fetch the parent daily content and find the phrase within it.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')
const navigation = require('../../utils/navigation')

Page({
  data: {
    // Route params
    phraseId: null,
    contentId: null,

    // Loading / error
    loading: true,
    error: false,
    errorMsg: '',

    // Phrase data
    phrase: '',
    explanation: '',
    examples: [],
    source: '',

    // Theme info from parent content
    themeZh: '',
    dateDisplay: '',

    // Mastery rating (1-5 stars)
    masteryRating: 0,
    isSubmittingRating: false,
    isLoggedIn: false,

    // Expanded example index for audio hint
    expandedExample: -1
  },

  onLoad: function (options) {
    var phraseId = options.id || options.phrase_id || null
    var contentId = options.content_id || options.contentId || null

    if (!phraseId) {
      this.setData({
        loading: false,
        error: true,
        errorMsg: '缺少短语ID参数'
      })
      return
    }

    this.setData({
      phraseId: phraseId,
      contentId: contentId,
      isLoggedIn: auth.isLoggedIn()
    })

    this._loadPhrase()
  },

  onShow: function () {
    // Refresh login state
    this.setData({ isLoggedIn: auth.isLoggedIn() })
  },

  onShareAppMessage: function () {
    var phrase = this.data.phrase || '英语短语'
    return {
      title: 'EasySpeak · ' + phrase,
      path: '/pages/phrase-detail/phrase-detail?id=' + this.data.phraseId +
            (this.data.contentId ? '&content_id=' + this.data.contentId : '')
    }
  },

  // ========================
  // Data Loading
  // ========================

  _loadPhrase: function () {
    var self = this
    var phraseId = this.data.phraseId
    var contentId = this.data.contentId

    if (contentId) {
      // We have the content_id — fetch content and find phrase
      self._fetchContentAndFindPhrase(contentId, phraseId)
    } else {
      // No content_id — try to find from recent daily cache
      self._findPhraseFromCache(phraseId)
    }
  },

  _fetchContentAndFindPhrase: function (contentId, phraseId) {
    var self = this
    self.setData({ loading: true, error: false })

    // Try cache first
    var cacheKey = storage.KEYS.CONTENT_CACHE_PREFIX + 'detail_' + contentId
    var cached = storage.getCache(cacheKey)

    if (cached) {
      var found = self._extractPhraseFromContent(cached, phraseId)
      if (found) {
        self._applyPhraseData(found, cached)
        self.setData({ loading: false })
        // Still refresh in background
      }
    }

    api.get('/daily/content/' + contentId)
      .then(function (data) {
        storage.setCache(cacheKey, data, storage.TTL.CONTENT_DETAIL)
        var found = self._extractPhraseFromContent(data, phraseId)
        if (found) {
          self._applyPhraseData(found, data)
          self.setData({ loading: false, error: false })
        } else {
          self.setData({
            loading: false,
            error: true,
            errorMsg: '未找到该短语'
          })
        }
      })
      .catch(function (err) {
        console.error('[PhraseDetail] Fetch failed:', err)
        if (cached && self.data.phrase) {
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

  _findPhraseFromCache: function (phraseId) {
    var self = this
    self.setData({ loading: true, error: false })

    // Search recent daily caches for the phrase
    var today = storage.formatDate(new Date())
    var foundPhrase = null
    var foundContent = null

    // Check today and recent dates
    for (var i = 0; i <= 3; i++) {
      var d = new Date(Date.now() - i * 24 * 60 * 60 * 1000)
      var dateStr = storage.formatDate(d)
      var dailyCache = storage.getDailyCache(dateStr)
      if (dailyCache) {
        var content = dailyCache.content || dailyCache
        if (content && content.phrases) {
          var found = self._findPhraseInList(content.phrases, phraseId)
          if (found) {
            foundPhrase = found
            foundContent = content
            break
          }
        }
      }
    }

    if (foundPhrase) {
      self._applyPhraseData(foundPhrase, foundContent)
      self.setData({ loading: false })
    } else {
      self.setData({
        loading: false,
        error: true,
        errorMsg: '未找到该短语，请返回重试'
      })
    }
  },

  _extractPhraseFromContent: function (data, phraseId) {
    var content = data.content || data
    var phrases = content.phrases || []
    return this._findPhraseInList(phrases, phraseId)
  },

  _findPhraseInList: function (phrases, phraseId) {
    var pid = parseInt(phraseId)
    for (var i = 0; i < phrases.length; i++) {
      if (phrases[i].id === pid || phrases[i].id === phraseId) {
        return phrases[i]
      }
    }
    return null
  },

  _applyPhraseData: function (rawPhrase, content) {
    var examples = [
      { en: rawPhrase.example_1 || '', cn: rawPhrase.example_1_cn || '' },
      { en: rawPhrase.example_2 || '', cn: rawPhrase.example_2_cn || '' },
      { en: rawPhrase.example_3 || '', cn: rawPhrase.example_3_cn || '' }
    ].filter(function (e) { return e.en })

    var contentData = content.content || content

    this.setData({
      phrase: rawPhrase.phrase || '',
      explanation: rawPhrase.explanation || '',
      examples: examples,
      source: rawPhrase.source || '',
      themeZh: contentData.theme_zh || '',
      dateDisplay: this._formatDate(contentData.date || ''),
      masteryRating: rawPhrase.mastery_level || rawPhrase.mastery || 0
    })
  },

  _formatDate: function (dateStr) {
    if (!dateStr) return ''
    var parts = dateStr.split('-')
    return parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日'
  },

  // ========================
  // Event Handlers
  // ========================

  onExampleToggle: function (e) {
    var index = e.currentTarget.dataset.index
    if (this.data.expandedExample === index) {
      this.setData({ expandedExample: -1 })
    } else {
      this.setData({ expandedExample: index })
    }
  },

  onRateStar: function (e) {
    var self = this
    if (!self.data.isLoggedIn) {
      wx.showToast({ title: '请先登录后再评分', icon: 'none', duration: 2000 })
      return
    }
    if (self.data.isSubmittingRating) return

    var rating = e.currentTarget.dataset.rating
    rating = parseInt(rating)
    if (rating < 1 || rating > 5) return

    self.setData({ isSubmittingRating: true })

    api.post('/progress/mastery', {
      phrase_id: self.data.phraseId,
      mastery_level: rating
    }).then(function (data) {
      self.setData({
        masteryRating: rating,
        isSubmittingRating: false
      })
      var labels = ['', '还不熟', '有点印象', '基本掌握', '比较熟练', '完全掌握']
      wx.showToast({
        title: labels[rating] || '评分成功',
        icon: 'success',
        duration: 1500
      })
    }).catch(function (err) {
      console.error('[PhraseDetail] Rate failed:', err)
      // Optimistic update locally
      self.setData({
        masteryRating: rating,
        isSubmittingRating: false
      })
      wx.showToast({ title: '已记录', icon: 'success', duration: 1000 })
    })
  },

  onShareToFriend: function () {
    var phrase = this.data.phrase || '这个短语'
    wx.showShareMenu({ withShareTicket: true })
    // Trigger share sheet
    // Note: onShareAppMessage handles the actual share card
    wx.showToast({ title: '请点击右上角分享给朋友', icon: 'none', duration: 2000 })
  },

  onRetry: function () {
    this._loadPhrase()
  },

  onBack: function () {
    navigation.safeNavigateBack({
      delta: 1,
      fallbackUrl: '/pages/library/library',
      fallbackIsTab: true
    })
  }
})
