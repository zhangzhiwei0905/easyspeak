/**
 * EasySpeak - Quiz Play Page (答题界面)
 * Handles quiz flow: generate → display → answer → submit → next → result
 */

var api = require('../../utils/api')
var auth = require('../../utils/auth')

// Timer config for lightning mode
var LIGHTNING_SECONDS = 180 // 3 minutes
var TIMER_INTERVAL = 1000

Page({
  data: {
    // Loading
    loading: true,
    loadError: false,
    errorMsg: '',

    // Quiz config (from page options)
    quizType: 'lightning',   // lightning | theme | wrong
    quizCount: 10,
    quizMode: 'normal',      // timed | normal
    contentId: '',

    // Questions
    questions: [],
    currentIndex: 0,
    totalQuestions: 0,

    // Current question
    question: null,
    questionType: '',   // phrase_meaning | word_phonetic | fill_blank
    questionText: '',

    // Options
    options: [],        // [{key: 'A', text: '...', isCorrect: false}, ...]

    // User interaction
    selectedKey: '',    // currently selected option key
    submitted: false,   // whether answer was submitted
    isCorrect: false,   // whether current answer is correct

    // Timer (lightning mode)
    isTimed: false,
    timeRemaining: LIGHTNING_SECONDS,
    timerDisplay: '03:00',
    timerWarning: false,

    // Results tracking
    results: [],        // [{question, correctAnswer, userAnswer, isCorrect}, ...]
    correctCount: 0
  },

  _timer: null,

  onLoad: function (options) {
    var type = options.type || 'lightning'
    var count = parseInt(options.count) || 10
    var contentId = options.contentId || ''
    var mode = options.mode || 'normal'
    var isTimed = mode === 'timed'

    this.setData({
      quizType: type,
      quizCount: count,
      contentId: contentId,
      quizMode: mode,
      isTimed: isTimed,
      timeRemaining: isTimed ? LIGHTNING_SECONDS : 0
    })

    this._generateQuiz()
  },

  onUnload: function () {
    this._clearTimer()
  },

  onHide: function () {
    // Pause timer when page is hidden
    this._clearTimer()
  },

  onShow: function () {
    // Resume timer if timed mode and quiz is active
    if (this.data.isTimed && this.data.questions.length > 0 && !this.data.submitted && this.data.currentIndex < this.data.totalQuestions) {
      this._startTimer()
    }
  },

  // ========================
  // Quiz Generation
  // ========================

  _generateQuiz: function () {
    var self = this
    self.setData({ loading: true, loadError: false })

    var body = {
      type: self.data.quizType,
      count: self.data.quizCount
    }

    if (self.data.contentId) {
      body.content_id = self.data.contentId
    }

    auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        self.setData({ loading: false, loadError: true, errorMsg: '请先登录' })
        return
      }
      return api.post('/quiz/generate', body)
    }).then(function (data) {
      if (!data || !Array.isArray(data) || data.length === 0) {
        self.setData({ loading: false, loadError: true, errorMsg: '没有可用的题目' })
        return
      }

      var questions = self._processQuestions(data)
      var firstQ = questions[0]

      self.setData({
        loading: false,
        questions: questions,
        totalQuestions: questions.length,
        currentIndex: 0,
        question: firstQ,
        questionType: firstQ.type,
        questionText: firstQ.text,
        options: firstQ.options
      })

      // Start timer for lightning mode
      if (self.data.isTimed) {
        self._startTimer()
      }
    }).catch(function (err) {
      console.error('[QuizPlay] Generate failed:', err)
      self.setData({
        loading: false,
        loadError: true,
        errorMsg: err.message || '生成题目失败'
      })
    })
  },

  _processQuestions: function (rawQuestions) {
    return rawQuestions.map(function (q) {
      var correctKey = q.answer || ''
      var options = (q.options || []).map(function (opt) {
        return {
          key: opt.key || '',
          text: opt.text || '',
          isCorrect: opt.key === correctKey
        }
      })

      return {
        id: q.question_id || q.id,
        type: q.quiz_type || q.type || 'phrase_meaning',
        text: q.question_text || q.question || q.text || '',
        options: options,
        correctAnswer: correctKey,
        explanation: q.explanation || '',
        hint: q.hint || ''
      }
    })
  },

  // ========================
  // Timer
  // ========================

  _startTimer: function () {
    var self = this
    self._clearTimer()
    self._timer = setInterval(function () {
      var remaining = self.data.timeRemaining - 1
      if (remaining <= 0) {
        remaining = 0
        self._clearTimer()
        self._onTimeUp()
      }
      var mins = Math.floor(remaining / 60)
      var secs = remaining % 60
      var display = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0')
      self.setData({
        timeRemaining: remaining,
        timerDisplay: display,
        timerWarning: remaining <= 30
      })
    }, TIMER_INTERVAL)
  },

  _clearTimer: function () {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  },

  _onTimeUp: function () {
    var self = this
    wx.showModal({
      title: '时间到！',
      content: '闪电测验时间已结束',
      showCancel: false,
      success: function () {
        self._finishQuiz()
      }
    })
  },

  // ========================
  // Answer Handling
  // ========================

  onSelectOption: function (e) {
    if (this.data.submitted) return
    var key = e.detail.key
    // Pre-compute the correct option text for feedback display
    var correctOpt = this.data.options.find(function (o) { return o.isCorrect })
    this.setData({
      selectedKey: key,
      correctOptionText: correctOpt ? correctOpt.key + '. ' + correctOpt.text : ''
    })
  },

  onSubmitAnswer: function () {
    if (this.data.submitted || !this.data.selectedKey) {
      if (!this.data.selectedKey) {
        wx.showToast({ title: '请先选择答案', icon: 'none' })
      }
      return
    }

    var self = this
    var selectedKey = self.data.selectedKey
    var options = self.data.options
    var correctOption = options.find(function (o) { return o.isCorrect })
    var isCorrect = correctOption && correctOption.key === selectedKey

    // Record result — store both key and full text for review
    var selectedOption = options.find(function (o) { return o.key === selectedKey })
    var correctKey = correctOption ? correctOption.key : ''
    var correctText = correctOption ? correctOption.text : self.data.question.correctAnswer
    var selectedText = selectedOption ? selectedOption.text : selectedKey

    var result = {
      question: self.data.questionText,
      type: self.data.questionType,
      options: options.map(function (o) { return { key: o.key, text: o.text, isCorrect: o.isCorrect } }),
      correctAnswer: correctKey + '. ' + correctText,
      userAnswer: selectedKey + '. ' + selectedText,
      userAnswerKey: selectedKey,
      isCorrect: isCorrect,
      hint: self.data.question.hint || ''
    }

    var results = self.data.results.concat([result])
    var correctCount = self.data.correctCount + (isCorrect ? 1 : 0)

    self.setData({
      submitted: true,
      isCorrect: isCorrect,
      results: results,
      correctCount: correctCount
    })

    // Submit to backend
    api.post('/quiz/submit', {
      answers: [{
        question_id: self.data.question.id,
        answer: selectedText,
        quiz_type: self.data.questionType
      }]
    }).catch(function (err) {
      console.warn('[QuizPlay] Submit answer failed:', err)
    })
  },

  onNextQuestion: function () {
    if (!this.data.submitted) return

    var nextIndex = this.data.currentIndex + 1

    // Check if quiz is finished
    if (nextIndex >= this.data.totalQuestions) {
      this._clearTimer()
      this._finishQuiz()
      return
    }

    var nextQ = this.data.questions[nextIndex]
    this.setData({
      currentIndex: nextIndex,
      question: nextQ,
      questionType: nextQ.type,
      questionText: nextQ.text,
      options: nextQ.options,
      selectedKey: '',
      submitted: false,
      isCorrect: false
    })
  },

  // ========================
  // Quiz Finish
  // ========================

  _finishQuiz: function () {
    var results = this.data.results
    var correctCount = this.data.correctCount
    var totalQuestions = this.data.totalQuestions

    // If we timed out mid-question, count unanswered as wrong
    if (results.length < totalQuestions) {
      var remaining = totalQuestions - results.length
      for (var i = 0; i < remaining; i++) {
        var q = this.data.questions[results.length + i]
        if (q) {
          results.push({
            question: q.text,
            type: q.type,
            options: q.options.map(function (o) { return { key: o.key, text: o.text, isCorrect: o.isCorrect } }),
            correctAnswer: q.correctAnswer || '',
            userAnswer: '未作答',
            userAnswerKey: '',
            isCorrect: false
          })
        }
      }
      totalQuestions = results.length
    }

    // Store results in globalData for quiz-result page
    var app = getApp()
    app.globalData.quizResult = {
      correct: correctCount,
      total: totalQuestions,
      results: results,
      quizType: this.data.quizType
    }

    wx.redirectTo({
      url: '/pages/quiz-result/quiz-result'
    })
  },

  // ========================
  // Retry on error
  // ========================

  onRetry: function () {
    this._generateQuiz()
  },

  onBack: function () {
    wx.navigateBack()
  }
})
