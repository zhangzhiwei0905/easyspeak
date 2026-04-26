/**
 * EasySpeak — Immersive Learning Session (沉浸式学习会话)
 *
 * Four-stage learning flow:
 *   Stage 1: Exposure  — show card, read aloud
 *   Stage 2: Comprehension — multiple-choice meaning quiz
 *   Stage 3: Practice  — fill-in-the-blank / reverse quiz
 *   Stage 4: Mastery   — delayed recall self-assessment
 *
 * After all stages, show a learning report.
 */

var api = require('../../utils/api')
var auth = require('../../utils/auth')
var storage = require('../../utils/storage')
var navigation = require('../../utils/navigation')

var BATCH_SIZE = 5
var MIN_EXPOSURE_MS = 4000 // minimum time on exposure card

Page({
  data: {
    // --- session meta ---
    loading: true,
    loadError: false,
    errorMsg: '',
    learnType: 'phrase', // 'phrase' or 'word'
    contentId: '',
    themeZh: '',
    themeEn: '',

    // --- overall phase ---
    // 'learning' | 'stage4' | 'report'
    phase: 'learning',

    // --- stage tracking (stages 1-3) ---
    stage: 1, // current stage: 1=exposure, 2=comprehension, 3=practice
    stageLabels: { 1: '认识', 2: '理解', 3: '练习' },

    // --- items ---
    allItems: [],       // all items from API
    queue: [],          // current working queue for stages 1-3
    retryQueue: [],     // items that need retry
    currentIndex: 0,    // index into queue
    currentItem: null,  // the item being displayed

    // --- progress counters ---
    totalItems: 0,
    processedCount: 0,  // items finished so far (across all stages)

    // --- stage 1: exposure ---
    canProceed: false,  // becomes true after MIN_EXPOSURE_MS

    // --- stage 2 & 3: quiz ---
    quizData: null,     // current quiz object {question, options, answer, hint}
    selectedKey: '',
    submitted: false,
    isCorrect: false,
    correctOptionText: '',

    // --- stage 4: mastery recall ---
    stage4Items: [],    // items for final recall round
    stage4Index: 0,
    stage4Item: null,
    stage4Flipped: false,
    stage4Mode: 'self', // 'self' or 'spelling'
    spellingInput: '',
    spellingSubmitted: false,
    spellingCorrect: false,

    // --- stats for report ---
    startTime: 0,
    firstPassCorrect: 0,
    retryCorrect: 0,
    masteryResults: [], // [{item_id, item_type, mastery}]

    // --- report ---
    report: null
  },

  _exposureTimer: null,
  _audioCtx: null,
  _attemptState: null,
  _correctAudio: null,
  _wrongAudio: null,

  // ================================================
  // Lifecycle
  // ================================================

  onLoad: function (options) {
    var contentId = options.content_id || options.contentId || ''
    var learnType = options.learn_type || options.learnType || 'phrase'
    var shouldResume = options.resume === '1' || options.resume === 'true'

    if (!contentId) {
      this.setData({ loading: false, loadError: true, errorMsg: '缺少内容参数' })
      return
    }

    this.setData({
      contentId: contentId,
      learnType: learnType,
      startTime: Date.now()
    })

    this._correctAudio = wx.createInnerAudioContext()
    this._correctAudio.src = '/audio/correct.wav'
    this._wrongAudio = wx.createInnerAudioContext()
    this._wrongAudio.src = '/audio/wrong.wav'

    if (shouldResume && this._restoreDraft(contentId, learnType)) {
      return
    }

    if (!shouldResume) {
      storage.removeLearnDraft(contentId, learnType)
    }
    this._createSession()
  },

  onUnload: function () {
    this._saveDraft()
    this._clearExposureTimer()
    this._destroyAudio()
    if (this._correctAudio) { try { this._correctAudio.stop(); this._correctAudio.destroy() } catch (e) {} }
    if (this._wrongAudio) { try { this._wrongAudio.stop(); this._wrongAudio.destroy() } catch (e) {} }
  },

  // ================================================
  // Session creation
  // ================================================

  _createSession: function () {
    var self = this
    self.setData({ loading: true, loadError: false })

    auth.ensureLogin().then(function () {
      return api.post('/learn/session', {
        content_id: parseInt(self.data.contentId),
        learn_type: self.data.learnType
      })
    }).then(function (data) {
      if (!data || !data.items || data.items.length === 0) {
        self.setData({ loading: false, loadError: true, errorMsg: '没有可学习的内容' })
        return
      }

      var items = data.items
      console.log('[LearnSession] API response items count:', items.length)
      console.log('[LearnSession] First item:', JSON.stringify(items[0]))
      console.log('[LearnSession] First item stage2_quiz:', JSON.stringify(items[0].stage2_quiz))

      self._attemptState = {}
      items.forEach(function (entry) {
        self._attemptState[entry.id] = {
          stage2FirstCorrect: false,
          stage3FirstCorrect: false,
          stage2Attempted: false,
          stage3Attempted: false,
          enteredRetry: false,
          completed: false
        }
      })

      self.setData({
        loading: false,
        themeZh: data.theme_zh || '',
        themeEn: data.theme_en || '',
        allItems: items,
        totalItems: items.length,
        queue: items.slice(),
        currentIndex: 0,
        currentItem: items[0],
        stage: 1,
        phase: 'learning',
        canProceed: false
      }, function () {
        self._saveDraft()
      })

      self._startExposureTimer()
      self._playItemAudio(items[0])
    }).catch(function (err) {
      console.error('[LearnSession] Create session failed:', err)
      self.setData({
        loading: false,
        loadError: true,
        errorMsg: err.message || '加载失败'
      })
    })
  },

  // ================================================
  // Stage 1: Exposure
  // ================================================

  _startExposureTimer: function () {
    var self = this
    self._clearExposureTimer()
    self.setData({ canProceed: false })
    self._exposureTimer = setTimeout(function () {
      self.setData({ canProceed: true })
    }, MIN_EXPOSURE_MS)
  },

  _clearExposureTimer: function () {
    if (this._exposureTimer) {
      clearTimeout(this._exposureTimer)
      this._exposureTimer = null
    }
  },

  _cleanPhraseText: function (text) {
    // Split on " / " and take only the first part
    if (text.indexOf(' / ') !== -1) {
      text = text.split(' / ')[0]
    }
    // Remove trailing ellipsis (… or ...)
    text = text.replace(/[.…]+$/, '')
    return text.trim()
  },

  _playItemAudio: function (item) {
    if (!item) return
    var text = ''
    if (item.type === 'phrase') {
      text = this._cleanPhraseText(item.phrase || '')
    } else {
      text = item.word || ''
    }
    if (!text) return

    var self = this
    this._destroyAudio()
    var audio = wx.createInnerAudioContext()
    this._audioCtx = audio

    var youdaoUrl = 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(text) + '&type=2'
    var baiduUrl = 'https://fanyi.baidu.com/gettts?lan=en&text=' + encodeURIComponent(text) + '&spd=2&source=web'
    var triedFallback = false

    audio.src = youdaoUrl
    audio.play()

    audio.onEnded(function () {})
    audio.onError(function (err) {
      console.error('[LearnSession] Audio error:', err)
      if (!triedFallback) {
        triedFallback = true
        console.log('[LearnSession] Trying Baidu TTS fallback for:', text)
        self._destroyAudio()
        var audio2 = wx.createInnerAudioContext()
        self._audioCtx = audio2
        audio2.src = baiduUrl
        audio2.play()
        audio2.onError(function (err2) {
          console.error('[LearnSession] Baidu TTS fallback also failed:', err2)
          // Silently fail — no toast
        })
      }
      // Silently fail on second error
    })
  },

  _destroyAudio: function () {
    if (this._audioCtx) {
      try { this._audioCtx.stop() } catch (e) {}
      try { this._audioCtx.destroy() } catch (e) {}
      this._audioCtx = null
    }
  },

  onPlayAudio: function () {
    this._playItemAudio(this.data.currentItem)
  },

  onExposureNext: function () {
    if (!this.data.canProceed) return
    // Move to Stage 2
    var item = this.data.currentItem
    var quiz = item.stage2_quiz
    console.log('[LearnSession] Stage2 quiz data:', JSON.stringify(quiz))
    if (quiz && quiz.options) {
      for (var i = 0; i < quiz.options.length; i++) {
        console.log('[LearnSession] Option', quiz.options[i].key, ':', JSON.stringify(quiz.options[i].text), quiz.options[i].key === quiz.answer ? '<-- CORRECT' : '')
      }
    }
    this.setData({
      stage: 2,
      quizData: quiz,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: ''
    }, this._saveDraft.bind(this))
  },

  // ================================================
  // Stage 2 & 3: Quiz interaction
  // ================================================

  onSelectOption: function (e) {
    if (this.data.submitted) return
    var key = e.currentTarget.dataset.key
    this.setData({ selectedKey: key }, this._saveDraft.bind(this))
  },

  onSubmitAnswer: function () {
    if (this.data.submitted || !this.data.selectedKey) {
      if (!this.data.selectedKey) {
        wx.showToast({ title: '请先选择答案', icon: 'none' })
      }
      return
    }

    var quiz = this.data.quizData
    var selectedKey = this.data.selectedKey
    var isCorrect = (selectedKey === quiz.answer)

    // Find correct option text
    var correctOpt = null
    for (var i = 0; i < quiz.options.length; i++) {
      if (quiz.options[i].key === quiz.answer) {
        correctOpt = quiz.options[i]
        break
      }
    }

    this.setData({
      submitted: true,
      isCorrect: isCorrect,
      correctOptionText: correctOpt ? correctOpt.key + '. ' + correctOpt.text : ''
    }, this._saveDraft.bind(this))

    // Haptic feedback
    if (isCorrect) {
      wx.vibrateShort({ type: 'light' })
      if (this._correctAudio) { this._correctAudio.stop(); this._correctAudio.play() }
    } else {
      wx.vibrateShort({ type: 'heavy' })
      if (this._wrongAudio) { this._wrongAudio.stop(); this._wrongAudio.play() }
    }
  },

  onQuizNext: function () {
    if (!this.data.submitted) return

    var stage = this.data.stage
    var isCorrect = this.data.isCorrect
    var item = this.data.currentItem
    var attempts = this._attemptState || {}
    var itemState = attempts[item.id] || {
      stage2FirstCorrect: false,
      stage3FirstCorrect: false,
      stage2Attempted: false,
      stage3Attempted: false,
      enteredRetry: false,
      completed: false
    }

    if (!isCorrect) {
      // Wrong answer: add to retry queue (will be re-tested)
      var retryQueue = this.data.retryQueue.slice()
      var exists = retryQueue.some(function (entry) {
        return entry.id === item.id
      })
      if (!exists) {
        retryQueue.push(item)
      }
      this.setData({ retryQueue: retryQueue })
      itemState.enteredRetry = true
    } else {
      if (stage === 2 && !itemState.stage2Attempted) {
        itemState.stage2FirstCorrect = true
      }
      if (stage === 3 && !itemState.stage3Attempted) {
        itemState.stage3FirstCorrect = true
      }
    }

    if (stage === 2 && !itemState.stage2Attempted) {
      itemState.stage2Attempted = true
    }
    if (stage === 3 && !itemState.stage3Attempted) {
      itemState.stage3Attempted = true
    }

    this._attemptState[item.id] = itemState

    if (stage === 2) {
      // Move to Stage 3 for correct answers, or repeat Stage 2 is handled via retry
      if (isCorrect) {
        var quiz3 = item.stage3_quiz
        this.setData({
          stage: 3,
          quizData: quiz3,
          selectedKey: '',
          submitted: false,
          isCorrect: false,
          correctOptionText: ''
        }, this._saveDraft.bind(this))
      } else {
        // Wrong in stage 2: move to next item, this one goes to retry
        this._advanceToNextItem()
      }
    } else if (stage === 3) {
      // Stage 3 done (correct or wrong) — move to next item
      if (isCorrect) {
        var updates = {}
        if (!itemState.completed) {
          if (itemState.stage2FirstCorrect && itemState.stage3FirstCorrect && !itemState.enteredRetry) {
            updates.firstPassCorrect = this.data.firstPassCorrect + 1
          } else if (itemState.enteredRetry) {
            updates.retryCorrect = this.data.retryCorrect + 1
          }
        }
        itemState.completed = true
        if (Object.keys(updates).length > 0) {
        this.setData(updates, this._saveDraft.bind(this))
      }
      }
      this._advanceToNextItem()
    }
  },

  _advanceToNextItem: function () {
    var nextIndex = this.data.currentIndex + 1
    var queue = this.data.queue

    if (nextIndex >= queue.length) {
      // Check retry queue
      if (this.data.retryQueue.length > 0) {
        // Shuffle retry items and start a new round
        var retryItems = this.data.retryQueue.slice()
        this._shuffle(retryItems)
        this.setData({
          queue: retryItems,
          retryQueue: [],
          currentIndex: 0,
          currentItem: retryItems[0],
          stage: 1,
          canProceed: false,
          selectedKey: '',
          submitted: false,
          isCorrect: false,
          retryCorrect: this.data.retryCorrect  // will increment below
        }, this._saveDraft.bind(this))
        this._startExposureTimer()
        this._playItemAudio(retryItems[0])
      } else {
        // All items passed stages 1-3 → enter Stage 4
        this._enterStage4()
      }
      return
    }

    var nextItem = queue[nextIndex]
    this.setData({
      currentIndex: nextIndex,
      currentItem: nextItem,
      stage: 1,
      canProceed: false,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: ''
    }, this._saveDraft.bind(this))
    this._startExposureTimer()
    this._playItemAudio(nextItem)
  },

  _shuffle: function (arr) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1))
      var tmp = arr[i]
      arr[i] = arr[j]
      arr[j] = tmp
    }
  },

  // ================================================
  // Stage 4: Mastery — delayed recall
  // ================================================

  _enterStage4: function () {
    var items = this.data.allItems.slice()
    this._shuffle(items)

    this.setData({
      phase: 'stage4',
      stage4Items: items,
      stage4Index: 0,
      stage4Item: items[0],
      stage4Flipped: false,
      stage4Mode: this._getStage4Mode(0),
      spellingInput: '',
      spellingSubmitted: false,
      spellingCorrect: false,
      masteryResults: []
    }, this._saveDraft.bind(this))
  },

  onFlipCard: function () {
    if (this.data.stage4Flipped) return
    this.setData({ stage4Flipped: true }, this._saveDraft.bind(this))

    // Play audio on flip
    this._playItemAudio(this.data.stage4Item)
  },

  _getStage4Mode: function (index) {
    // 混合题型：奇数项进入拼写题，偶数项保留“点击显示答案 + 自评”
    return index % 2 === 1 ? 'spelling' : 'self'
  },

  _getItemAnswerText: function (item) {
    if (!item) return ''
    return item.type === 'phrase' ? (item.phrase || '') : (item.word || '')
  },

  _normalizeSpelling: function (text) {
    return (text || '').toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9]+/g, '')
  },

  onSpellingInput: function (e) {
    this.setData({ spellingInput: e.detail.value || '' }, this._saveDraft.bind(this))
  },

  onSubmitSpelling: function () {
    if (this.data.spellingSubmitted) return
    var input = (this.data.spellingInput || '').trim()
    if (!input) {
      wx.showToast({ title: '请先输入答案', icon: 'none' })
      return
    }
    var answer = this._getItemAnswerText(this.data.stage4Item)
    var isCorrect = this._normalizeSpelling(input) === this._normalizeSpelling(answer)
    this.setData({
      spellingSubmitted: true,
      spellingCorrect: isCorrect,
      stage4Flipped: true
    }, this._saveDraft.bind(this))
    if (isCorrect) {
      wx.vibrateShort({ type: 'light' })
      this._playItemAudio(this.data.stage4Item)
      if (this._correctAudio) { this._correctAudio.stop(); this._correctAudio.play() }
    } else {
      wx.vibrateShort({ type: 'heavy' })
      if (this._wrongAudio) { this._wrongAudio.stop(); this._wrongAudio.play() }
    }
  },

  onSpellingNext: function () {
    if (!this.data.spellingSubmitted) return
    this._recordStage4Mastery(this.data.spellingCorrect ? 4 : 0)
  },

  _recordStage4Mastery: function (mastery) {
    var item = this.data.stage4Item

    // Record this item's mastery
    var results = this.data.masteryResults.slice()
    results.push({
      item_id: item.id,
      item_type: item.type,
      mastery: mastery
    })

    var nextIndex = this.data.stage4Index + 1

    if (nextIndex >= this.data.stage4Items.length) {
      // All done — submit and show report
      this.setData({ masteryResults: results }, this._saveDraft.bind(this))
      this._submitAndShowReport(results)
    } else {
      var nextItem = this.data.stage4Items[nextIndex]
      this.setData({
        masteryResults: results,
        stage4Index: nextIndex,
        stage4Item: nextItem,
        stage4Flipped: false,
        stage4Mode: this._getStage4Mode(nextIndex),
        spellingInput: '',
        spellingSubmitted: false,
        spellingCorrect: false
      }, this._saveDraft.bind(this))
    }
  },

  onMasterySelect: function (e) {
    var mastery = parseInt(e.currentTarget.dataset.mastery)
    this._recordStage4Mastery(mastery)
  },

  // ================================================
  // Local draft persistence
  // ================================================

  _buildDraft: function () {
    if (this.data.loading || this.data.loadError || this.data.phase === 'report') return null
    if (!this.data.contentId || !this.data.learnType || this.data.allItems.length === 0) return null

    return {
      version: 1,
      savedAt: Date.now(),
      contentId: this.data.contentId,
      learnType: this.data.learnType,
      themeZh: this.data.themeZh,
      themeEn: this.data.themeEn,
      phase: this.data.phase,
      stage: this.data.stage,
      allItems: this.data.allItems,
      queue: this.data.queue,
      retryQueue: this.data.retryQueue,
      currentIndex: this.data.currentIndex,
      currentItem: this.data.currentItem,
      totalItems: this.data.totalItems,
      canProceed: this.data.canProceed,
      quizData: this.data.quizData,
      selectedKey: this.data.selectedKey,
      submitted: this.data.submitted,
      isCorrect: this.data.isCorrect,
      correctOptionText: this.data.correctOptionText,
      stage4Items: this.data.stage4Items,
      stage4Index: this.data.stage4Index,
      stage4Item: this.data.stage4Item,
      stage4Flipped: this.data.stage4Flipped,
      stage4Mode: this.data.stage4Mode,
      spellingInput: this.data.spellingInput,
      spellingSubmitted: this.data.spellingSubmitted,
      spellingCorrect: this.data.spellingCorrect,
      startTime: this.data.startTime,
      firstPassCorrect: this.data.firstPassCorrect,
      retryCorrect: this.data.retryCorrect,
      masteryResults: this.data.masteryResults,
      attemptState: this._attemptState || {}
    }
  },

  _saveDraft: function () {
    var draft = this._buildDraft()
    if (!draft) return
    storage.setLearnDraft(this.data.contentId, this.data.learnType, draft)
  },

  _clearDraft: function () {
    if (!this.data.contentId || !this.data.learnType) return
    storage.removeLearnDraft(this.data.contentId, this.data.learnType)
  },

  _restoreDraft: function (contentId, learnType) {
    var draft = storage.getLearnDraft(contentId, learnType)
    if (!draft || draft.version !== 1 || !draft.allItems || draft.allItems.length === 0) {
      return false
    }

    this._attemptState = draft.attemptState || {}
    this.setData({
      loading: false,
      loadError: false,
      errorMsg: '',
      contentId: String(contentId),
      learnType: learnType,
      themeZh: draft.themeZh || '',
      themeEn: draft.themeEn || '',
      phase: draft.phase || 'learning',
      stage: draft.stage || 1,
      allItems: draft.allItems || [],
      queue: draft.queue || [],
      retryQueue: draft.retryQueue || [],
      currentIndex: draft.currentIndex || 0,
      currentItem: draft.currentItem || null,
      totalItems: draft.totalItems || (draft.allItems || []).length,
      canProceed: !!draft.canProceed,
      quizData: draft.quizData || null,
      selectedKey: draft.selectedKey || '',
      submitted: !!draft.submitted,
      isCorrect: !!draft.isCorrect,
      correctOptionText: draft.correctOptionText || '',
      stage4Items: draft.stage4Items || [],
      stage4Index: draft.stage4Index || 0,
      stage4Item: draft.stage4Item || null,
      stage4Flipped: !!draft.stage4Flipped,
      stage4Mode: draft.stage4Mode || this._getStage4Mode(draft.stage4Index || 0),
      spellingInput: draft.spellingInput || '',
      spellingSubmitted: !!draft.spellingSubmitted,
      spellingCorrect: !!draft.spellingCorrect,
      startTime: draft.startTime || Date.now(),
      firstPassCorrect: draft.firstPassCorrect || 0,
      retryCorrect: draft.retryCorrect || 0,
      masteryResults: draft.masteryResults || [],
      report: null
    })

    if (this.data.phase === 'learning' && this.data.stage === 1 && !this.data.canProceed) {
      this._startExposureTimer()
    }
    if (this.data.phase === 'learning' && this.data.currentItem) {
      this._playItemAudio(this.data.currentItem)
    }
    return true
  },

  // ================================================
  // Report submission
  // ================================================

  _submitAndShowReport: function (results) {
    var self = this
    var durationSeconds = Math.round((Date.now() - self.data.startTime) / 1000)

    // Calculate mastery distribution
    var dist = { forgot: 0, fuzzy: 0, remembered: 0, solid: 0 }
    for (var i = 0; i < results.length; i++) {
      var m = results[i].mastery
      if (m <= 0) dist.forgot++
      else if (m <= 1) dist.fuzzy++
      else if (m <= 3) dist.remembered++
      else dist.solid++
    }

    var totalItems = self.data.totalItems
    var firstPassCorrect = self.data.firstPassCorrect
    var retryCorrect = self.data.retryCorrect

    var report = {
      totalItems: totalItems,
      firstPassCorrect: firstPassCorrect,
      retryCorrect: retryCorrect,
      durationSeconds: durationSeconds,
      durationDisplay: self._formatDuration(durationSeconds),
      distribution: dist,
      firstPassRate: totalItems > 0
        ? Math.round((firstPassCorrect / totalItems) * 100)
        : 0,
      finalPassRate: totalItems > 0
        ? Math.round(((firstPassCorrect + retryCorrect) / totalItems) * 100)
        : 0
    }

    self.setData({
      phase: 'report',
      report: report
    })
    self._clearDraft()

    // Submit progress to backend (async, don't block UI)
    api.post('/learn/progress', {
      content_id: parseInt(self.data.contentId),
      learn_type: self.data.learnType,
      items: results
    }).catch(function (err) {
      console.warn('[LearnSession] Failed to submit progress:', err)
    })

    // Submit report
    api.post('/learn/report', {
      content_id: parseInt(self.data.contentId),
      learn_type: self.data.learnType,
      total_items: report.totalItems,
      first_pass_correct: report.firstPassCorrect,
      retry_correct: report.retryCorrect,
      duration_seconds: durationSeconds,
      mastery_distribution: dist
    }).then(function (res) {
      // Update streak display
      if (res && res.study_streak) {
        self.setData({
          'report.studyStreak': res.study_streak
        })
      }
      storage.recordStudyDay()
    }).catch(function (err) {
      console.warn('[LearnSession] Failed to submit report:', err)
      storage.recordStudyDay()
    })
  },

  _formatDuration: function (seconds) {
    var mins = Math.floor(seconds / 60)
    var secs = seconds % 60
    return mins + ' 分 ' + secs + ' 秒'
  },

  // ================================================
  // Navigation
  // ================================================

  onExit: function () {
    var self = this
    if (self.data.phase === 'report') {
      navigation.safeNavigateBack({
        fallbackUrl: '/pages/index/index',
        fallbackIsTab: true
      })
      return
    }

    wx.showModal({
      title: '确认退出',
      content: '学习进度将不会保存，确定退出吗？',
      confirmText: '退出',
      cancelText: '继续学习',
      success: function (res) {
        if (res.confirm) {
          navigation.safeNavigateBack({
            fallbackUrl: '/pages/index/index',
            fallbackIsTab: true
          })
        }
      }
    })
  },

  onBackToHome: function () {
    navigation.safeNavigateBack({
      fallbackUrl: '/pages/index/index',
      fallbackIsTab: true
    })
  },

  onRetry: function () {
    this._clearDraft()
    this._createSession()
  },

  onShareResult: function () {
    // Handled by onShareAppMessage
  },

  onShareAppMessage: function () {
    var report = this.data.report
    if (report) {
      return {
        title: '我刚学了' + report.totalItems + '个' + (this.data.learnType === 'phrase' ? '短语' : '单词') + '，一次通过率' + report.firstPassRate + '%！',
        path: '/pages/index/index'
      }
    }
    return {
      title: 'EasySpeak · 沉浸式英语学习',
      path: '/pages/index/index'
    }
  }
})
