const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

Page({
  data: {
    mode: 'overview',

    loading: true,
    currentMonth: '',
    calendarData: [],
    summary: {
      forgetting_count: 0,
      consolidating_count: 0,
      mastered_count: 0,
      new_count: 0
    },
    dueCount: 0,
    todayReviewCount: 0,
    overviewLoadFailed: false,

    dueItems: [],
    quizQueue: [],
    currentIndex: 0,
    totalQuestionCount: 0,
    currentItem: {},
    reviewStage: 2,
    reviewStageLabel: '理解',
    quizData: null,
    selectedKey: '',
    submitted: false,
    isCorrect: false,
    correctOptionText: '',
    finalQuiz: null,
    wordSlots: [],
    availableTiles: [],
    wordSelectSubmitted: false,
    spellingSlots: [],
    keyboardLetters: [],
    spellingSubmitted: false,
    spellingCorrect: false,
    submitting: false,

    summaryResult: {
      reviewedCount: 0,
      avgMastery: '0.0',
      masteryLabel: '',
      masteryLevel: '',
      distribution: []
    },

    showDayDetail: false,
    dayDetail: {}
  },

  _masteryRatings: [],
  _reviewResults: {},
  _completedReviewKeys: {},

  onLoad() {
    this._initPage()
  },

  onShow() {
    if (this.data.mode === 'overview') {
      this._loadOverviewData()
    }
  },

  onPullDownRefresh() {
    this._loadOverviewData()
      .then(function () {
        wx.stopPullDownRefresh()
      })
      .catch(function () {
        wx.stopPullDownRefresh()
      })
  },

  _initPage() {
    var now = new Date()
    var y = now.getFullYear()
    var m = String(now.getMonth() + 1).padStart(2, '0')
    this.setData({
      currentMonth: y + '-' + m
    })
    this._loadOverviewData()
  },

  _loadOverviewData() {
    var self = this
    var parts = self.data.currentMonth.split('-')
    var params = {
      year: parseInt(parts[0], 10),
      month: parseInt(parts[1], 10)
    }

    self.setData({
      loading: true,
      overviewLoadFailed: false
    })

    return auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          self.setData({
            loading: false,
            overviewLoadFailed: true
          })
          return Promise.reject(new Error('login required'))
        }

        return api.get('/review/overview', params)
      })
      .then(function (res) {
        var rawCalendar = res.calendar_dates || []
        // Handle both formats: old API returns strings, new API returns objects
        var calendarData = []
        var dateStrings = []
        for (var i = 0; i < rawCalendar.length; i++) {
          var item = rawCalendar[i]
          if (typeof item === 'string') {
            calendarData.push({ date: item, has_content: false, learned: false, reviewed: 0 })
            dateStrings.push(item)
          } else {
            calendarData.push(item)
            dateStrings.push(item.date)
          }
        }

        self.setData({
          loading: false,
          overviewLoadFailed: false,
          calendarData: calendarData,
          dueCount: res.due_count || 0,
          todayReviewCount: res.today_review_count || res.due_count || 0,
          summary: res.memory_summary || {
            forgetting_count: 0,
            consolidating_count: 0,
            mastered_count: 0,
            new_count: 0
          }
        })

        if (dateStrings.length > 0) {
          storage.set(storage.KEYS.STUDY_CALENDAR, dateStrings)
        }
      })
      .catch(function (err) {
        console.error('[Review] Failed to load overview:', err)
        self.setData({
          loading: false,
          overviewLoadFailed: true
        })
      })
  },

  onMonthChange(e) {
    var year = e.detail.year
    var month = e.detail.month
    var m = String(month).padStart(2, '0')
    this.setData({ currentMonth: year + '-' + m })
    this._loadOverviewData()
  },

  onDayTap(e) {
    var dayData = e.detail.dayData
    if (!dayData || !dayData.dateStr) return
    if (dayData.status === 'empty') return
    if (dayData.status === 'none' && !dayData.reviewed) return

    this.setData({
      showDayDetail: true,
      dayDetail: {
        dateStr: dayData.dateStr,
        hasReview: (dayData.reviewed || 0) > 0,
        hasContent: !!(dayData.themeZh || dayData.phraseCount || dayData.wordCount),
        themeZh: dayData.themeZh || '',
        phraseCount: dayData.phraseCount || 0,
        wordCount: dayData.wordCount || 0,
        firstPassRate: dayData.firstPassRate,
        avgMastery: dayData.avgMastery || 0,
        reviewed: dayData.reviewed || 0,
        reviewedCount: dayData.reviewedCount || dayData.reviewed || 0,
        reviewPhraseCount: dayData.reviewPhraseCount || 0,
        reviewWordCount: dayData.reviewWordCount || 0,
        forgotCount: dayData.forgotCount || 0,
        fuzzyCount: dayData.fuzzyCount || 0,
        rememberedCount: dayData.rememberedCount || 0,
        solidCount: dayData.solidCount || 0,
        status: dayData.status
      }
    })
  },

  closeDayDetail() {
    this.setData({ showDayDetail: false })
  },

  startReview() {
    var self = this
    if (self.data.loading) return

    wx.showLoading({ title: '加载复习内容...' })
    auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          wx.hideLoading()
          return Promise.reject(new Error('login required'))
        }
        return api.get('/review/due')
      })
      .then(function (res) {
        wx.hideLoading()
        var items = res.items || []

        if (items.length === 0) {
          wx.showToast({ title: '暂无待复习内容', icon: 'none' })
          self._loadOverviewData()
          return
        }

        var queue = self._buildReviewQueue(items)
        self._masteryRatings = []
        self._reviewResults = {}
        self._completedReviewKeys = {}
        self.setData({
          mode: 'session',
          dueItems: items,
          quizQueue: queue,
          currentIndex: 0,
          totalQuestionCount: queue.length,
          submitting: false
        })
        self._loadQueueQuestion(0)
      })
      .catch(function (err) {
        wx.hideLoading()
        console.error('[Review] Failed to load due items:', err)
        wx.showToast({ title: '加载失败，请重试', icon: 'none' })
      })
  },

  _resultKey(item) {
    return item.item_type + ':' + item.id
  },

  _shuffleList(list) {
    var arr = list.slice()
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1))
      var tmp = arr[i]
      arr[i] = arr[j]
      arr[j] = tmp
    }
    return arr
  },

  _buildReviewQueue(items) {
    var queue = []
    for (var i = 0; i < items.length; i++) {
      var item = items[i]
      queue.push({ item: item, stage: 2 })
      queue.push({ item: item, stage: 3 })
      queue.push({ item: item, stage: 4 })
    }
    queue = this._shuffleList(queue)

    // 尽量避免同一个单词/短语的题目连着出现；如果随机后相邻，就向后找一个不同 item 交换。
    for (var q = 1; q < queue.length; q++) {
      if (this._resultKey(queue[q].item) !== this._resultKey(queue[q - 1].item)) continue
      for (var k = q + 1; k < queue.length; k++) {
        if (this._resultKey(queue[k].item) !== this._resultKey(queue[q - 1].item)) {
          var tmp = queue[q]
          queue[q] = queue[k]
          queue[k] = tmp
          break
        }
      }
    }
    return queue
  },

  _loadQueueQuestion(index) {
    var entry = this.data.quizQueue[index]
    if (!entry) {
      this._showSummary()
      return
    }
    var item = entry.item
    var stage = entry.stage
    var label = stage === 2 ? '理解' : (stage === 3 ? '练习' : '确认')
    var base = {
      currentIndex: index,
      currentItem: item,
      reviewStage: stage,
      reviewStageLabel: label,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: '',
      quizData: null,
      finalQuiz: null,
      wordSlots: [],
      availableTiles: [],
      wordSelectSubmitted: false,
      spellingSlots: [],
      keyboardLetters: [],
      spellingSubmitted: false,
      spellingCorrect: false,
      submitting: false
    }
    if (stage === 2) {
      base.quizData = item.stage2_quiz
      this.setData(base)
      return
    }
    if (stage === 3) {
      base.quizData = item.stage3_quiz
      this.setData(base)
      return
    }
    this.setData(base)
    this._enterFinalQuiz()
  },

  _markStageResult(stage, correct) {
    var item = this.data.currentItem
    var key = this._resultKey(item)
    if (!this._reviewResults[key]) {
      this._reviewResults[key] = { stage2: undefined, stage3: undefined, final: undefined }
    }
    this._reviewResults[key][stage] = !!correct
  },

  onReviewSelectOption(e) {
    if (this.data.submitted) return
    this.setData({ selectedKey: e.currentTarget.dataset.key })
  },

  onReviewSubmitChoice() {
    if (this.data.submitted) return
    if (!this.data.selectedKey) {
      wx.showToast({ title: '请先选择答案', icon: 'none' })
      return
    }
    var quiz = this.data.quizData || {}
    var selectedKey = this.data.selectedKey
    var isCorrect = selectedKey === quiz.answer
    var correctText = ''
    var options = quiz.options || []
    for (var i = 0; i < options.length; i++) {
      if (options[i].key === quiz.answer) {
        correctText = options[i].key + '. ' + options[i].text
        break
      }
    }
    this._markStageResult(this.data.reviewStage === 2 ? 'stage2' : 'stage3', isCorrect)
    this.setData({
      submitted: true,
      isCorrect: isCorrect,
      correctOptionText: correctText
    })
    wx.vibrateShort({ type: isCorrect ? 'light' : 'heavy' })
  },

  onReviewChoiceNext() {
    if (!this.data.submitted) return
    this._advanceAfterQuestion()
  },

  _enterFinalQuiz() {
    var item = this.data.currentItem
    var quiz = item.final_quiz || {}
    if (quiz.type === 'word_select') {
      var words = (quiz.correct_phrase || item.text || '').split(' ')
      var slots = words.map(function () { return { text: '', isCorrect: null } })
      var tiles = (quiz.word_tiles || words).map(function (text) { return { text: text, used: false } })
      this.setData({
        reviewStage: 4,
        reviewStageLabel: '确认',
        finalQuiz: quiz,
        wordSlots: slots,
        availableTiles: tiles,
        wordSelectSubmitted: false,
        spellingSlots: [],
        keyboardLetters: [],
        spellingSubmitted: false,
        spellingCorrect: false
      })
      return
    }

    var answer = quiz.answer || item.text || ''
    var chars = []
    for (var i = 0; i < answer.length; i++) {
      if (/[a-zA-Z]/.test(answer[i])) {
        chars.push({ text: '', expected: answer[i].toLowerCase(), isCorrect: null })
      }
    }
    var letters = (quiz.letters || chars.map(function (slot) { return slot.expected })).map(function (letter) {
      return { text: letter, used: false }
    })
    this.setData({
      reviewStage: 4,
      reviewStageLabel: '确认',
      finalQuiz: quiz,
      wordSlots: [],
      availableTiles: [],
      wordSelectSubmitted: false,
      spellingSlots: chars,
      keyboardLetters: letters,
      spellingSubmitted: false,
      spellingCorrect: false
    })
  },

  onReviewWordTileTap(e) {
    if (this.data.wordSelectSubmitted) return
    var tileIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()
    if (!tiles[tileIndex] || tiles[tileIndex].used) return
    var emptyIndex = -1
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) { emptyIndex = i; break }
    }
    if (emptyIndex === -1) return
    slots[emptyIndex] = { text: tiles[tileIndex].text, isCorrect: null }
    tiles[tileIndex] = { text: tiles[tileIndex].text, used: true }
    this.setData({ wordSlots: slots, availableTiles: tiles })
    if (slots.every(function (slot) { return !!slot.text })) {
      var self = this
      setTimeout(function () { self._checkReviewWordSelect() }, 250)
    }
  },

  onReviewSlotTap(e) {
    if (this.data.wordSelectSubmitted) return
    var slotIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()
    var removedText = slots[slotIndex] && slots[slotIndex].text
    if (!removedText) return
    slots[slotIndex] = { text: '', isCorrect: null }
    for (var i = 0; i < tiles.length; i++) {
      if (tiles[i].text === removedText && tiles[i].used) {
        tiles[i] = { text: removedText, used: false }
        break
      }
    }
    this.setData({ wordSlots: slots, availableTiles: tiles })
  },

  _checkReviewWordSelect() {
    var quiz = this.data.finalQuiz || {}
    var correctWords = (quiz.correct_phrase || '').split(' ')
    var allCorrect = true
    var slots = this.data.wordSlots.map(function (slot, i) {
      var correct = (slot.text || '').toLowerCase() === (correctWords[i] || '').toLowerCase()
      if (!correct) allCorrect = false
      return { text: slot.text, isCorrect: correct }
    })
    this._markStageResult('final', allCorrect)
    this.setData({ wordSlots: slots, wordSelectSubmitted: true })
    wx.vibrateShort({ type: allCorrect ? 'light' : 'heavy' })
  },

  onKeyboardLetterTap(e) {
    if (this.data.spellingSubmitted) return
    var index = e.currentTarget.dataset.index
    var letters = this.data.keyboardLetters.slice()
    if (!letters[index] || letters[index].used) return
    var slots = this.data.spellingSlots.slice()
    var emptyIndex = -1
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) { emptyIndex = i; break }
    }
    if (emptyIndex === -1) return
    slots[emptyIndex] = { text: letters[index].text, expected: slots[emptyIndex].expected, isCorrect: null, keyIndex: index }
    letters[index] = { text: letters[index].text, used: true }
    this.setData({ spellingSlots: slots, keyboardLetters: letters })
    if (slots.every(function (slot) { return !!slot.text })) {
      var self = this
      setTimeout(function () { self._checkSpellingKeyboard() }, 250)
    }
  },

  onSpellingSlotTap(e) {
    if (this.data.spellingSubmitted) return
    var slotIndex = e.currentTarget.dataset.index
    var slots = this.data.spellingSlots.slice()
    var letters = this.data.keyboardLetters.slice()
    var slot = slots[slotIndex]
    if (!slot || !slot.text) return
    if (slot.keyIndex !== undefined && letters[slot.keyIndex]) {
      letters[slot.keyIndex] = { text: letters[slot.keyIndex].text, used: false }
    }
    slots[slotIndex] = { text: '', expected: slot.expected, isCorrect: null }
    this.setData({ spellingSlots: slots, keyboardLetters: letters })
  },

  _checkSpellingKeyboard() {
    var allCorrect = true
    var slots = this.data.spellingSlots.map(function (slot) {
      var correct = (slot.text || '').toLowerCase() === (slot.expected || '').toLowerCase()
      if (!correct) allCorrect = false
      return { text: slot.text, expected: slot.expected, isCorrect: correct, keyIndex: slot.keyIndex }
    })
    this._markStageResult('final', allCorrect)
    this.setData({ spellingSlots: slots, spellingSubmitted: true, spellingCorrect: allCorrect })
    wx.vibrateShort({ type: allCorrect ? 'light' : 'heavy' })
  },

  onFinalNext() {
    var quiz = this.data.finalQuiz || {}
    if (quiz.type === 'word_select' && !this.data.wordSelectSubmitted) return
    if (quiz.type === 'spelling_keyboard' && !this.data.spellingSubmitted) return
    this._advanceAfterQuestion()
  },

  _isItemReadyToComplete(item) {
    var result = this._reviewResults[this._resultKey(item)] || {}
    return result.stage2 !== undefined && result.stage3 !== undefined && result.final !== undefined
  },

  _advanceAfterQuestion() {
    var item = this.data.currentItem
    if (this._isItemReadyToComplete(item) && !this._completedReviewKeys[this._resultKey(item)]) {
      this._completeReviewItemThenAdvance(item)
      return
    }
    this._goNextQueueQuestion()
  },

  _goNextQueueQuestion() {
    var nextIndex = this.data.currentIndex + 1
    if (nextIndex >= this.data.quizQueue.length) {
      this._showSummary()
      return
    }
    this._loadQueueQuestion(nextIndex)
  },

  _completeReviewItemThenAdvance(item) {
    var self = this
    if (self.data.submitting) return
    var key = self._resultKey(item)
    var result = self._reviewResults[key] || {}
    var correctCount = (result.stage2 ? 1 : 0) + (result.stage3 ? 1 : 0) + (result.final ? 1 : 0)
    var mastery = correctCount >= 3 ? 4 : (correctCount === 2 ? 3 : (correctCount === 1 ? 1 : 0))
    self.setData({ submitting: true })
    api.post('/review/complete', {
      item_id: item.id,
      item_type: item.item_type,
      mastery: mastery
    }).then(function () {
      self._completedReviewKeys[key] = true
      self._masteryRatings.push({ text: item.text, mastery: mastery })
      storage.recordStudyDay()
      self._goNextQueueQuestion()
    }).catch(function (err) {
      console.error('[Review] Failed to submit review quiz:', err)
      self.setData({ submitting: false })
      wx.showToast({ title: '提交失败，请重试', icon: 'none' })
    })
  },

  flipCard() {
    this.setData({
      isFlipped: !this.data.isFlipped
    })
  },

  selectMastery(e) {
    var self = this
    if (self.data.submitting) return

    var mastery = parseInt(e.currentTarget.dataset.mastery, 10)
    var currentItem = self.data.currentItem

    self.setData({ submitting: true })

    api.post('/review/complete', {
      item_id: currentItem.id,
      item_type: currentItem.item_type,
      mastery: mastery
    })
      .then(function () {
        self._masteryRatings.push({
          text: currentItem.text,
          mastery: mastery
        })

        storage.recordStudyDay()

        var nextIndex = self.data.currentIndex + 1
        if (nextIndex >= self.data.dueItems.length) {
          self._showSummary()
          return
        }

        self.setData({
          currentIndex: nextIndex,
          currentItem: self.data.dueItems[nextIndex],
          isFlipped: false,
          submitting: false
        })
      })
      .catch(function (err) {
        console.error('[Review] Failed to submit mastery:', err)
        self.setData({ submitting: false })
        wx.showToast({ title: '提交失败，请重试', icon: 'none' })
      })
  },

  _showSummary() {
    var ratings = this._masteryRatings
    var totalCount = ratings.length

    if (totalCount === 0) {
      this.setData({
        mode: 'summary',
        submitting: false,
        summaryResult: {
          reviewedCount: 0,
          avgMastery: '0.0',
          masteryLabel: '无数据',
          masteryLevel: 'none',
          distribution: []
        }
      })
      return
    }

    var sum = 0
    for (var i = 0; i < ratings.length; i++) {
      sum += ratings[i].mastery
    }
    var avg = sum / totalCount

    var masteryLabel = '需要复习'
    var masteryLevel = 'poor'
    if (avg >= 3.5) {
      masteryLabel = '太棒了！'
      masteryLevel = 'excellent'
    } else if (avg >= 2.5) {
      masteryLabel = '不错哦！'
      masteryLevel = 'good'
    } else if (avg >= 1.5) {
      masteryLabel = '继续加油'
      masteryLevel = 'fair'
    }

    var labels = [
      { level: 0, emoji: '😫', label: '完全忘了' },
      { level: 1, emoji: '😕', label: '有点印象' },
      { level: 2, emoji: '🤔', label: '想起来了' },
      { level: 3, emoji: '😊', label: '比较熟悉' },
      { level: 4, emoji: '🎯', label: '完全掌握' }
    ]

    var distribution = labels.map(function (entry) {
      var count = ratings.filter(function (item) {
        return item.mastery === entry.level
      }).length
      return {
        level: entry.level,
        emoji: entry.emoji,
        label: entry.label,
        count: count,
        pct: totalCount > 0 ? Math.round((count / totalCount) * 100) : 0
      }
    })

    this.setData({
      mode: 'summary',
      submitting: false,
      summaryResult: {
        reviewedCount: totalCount,
        avgMastery: avg.toFixed(1),
        masteryLabel: masteryLabel,
        masteryLevel: masteryLevel,
        distribution: distribution
      }
    })
  },

  exitSession() {
    var self = this
    var reviewed = self._masteryRatings.length
    var total = self.data.dueItems.length

    if (reviewed > 0 && reviewed < total) {
      wx.showModal({
        title: '确认退出',
        content: '已完成 ' + reviewed + '/' + total + ' 项，确定退出吗？',
        confirmText: '退出',
        cancelText: '继续复习',
        success: function (res) {
          if (res.confirm) {
            self._showSummary()
          }
        }
      })
      return
    }

    self.backToOverview()
  },

  reviewAgain() {
    this.setData({ mode: 'overview' })
    this.startReview()
  },

  backToOverview() {
    this._masteryRatings = []
    this.setData({
      mode: 'overview',
      quizQueue: [],
      currentIndex: 0,
      totalQuestionCount: 0,
      currentItem: {},
      isFlipped: false,
      submitting: false
    })
    this._loadOverviewData()
  },

  goToQuiz() {
    wx.switchTab({
      url: '/pages/quiz/quiz'
    })
  },

  onShareAppMessage() {
    if (this.data.mode === 'summary') {
      var result = this.data.summaryResult
      return {
        title: '我刚刚复习了' + result.reviewedCount + '项内容，掌握度' + result.avgMastery + '！',
        path: '/pages/review/review'
      }
    }

    return {
      title: 'EasySpeak · 智能复习',
      path: '/pages/review/review'
    }
  }
})
