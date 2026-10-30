/* Adapted from the first-party motion-refined study; no provider or API calls. */
(function () {
  'use strict';
  var progress = document.getElementById('scrollProgress');
  var header = document.getElementById('header');
  var hero = document.querySelector('.hero');
  var menu = document.getElementById('menuToggle');
  var mobile = document.getElementById('mobileNav');
  var motion = matchMedia('(prefers-reduced-motion: reduce)');
  var desktop = matchMedia('(min-width: 761px)');
  var motionButton = document.getElementById('motionToggle');
  var manualPause = false;
  var heroVisible = true;
  function updateMotion() {
    motionButton.hidden = motion.matches || !desktop.matches;
    motionButton.textContent = manualPause ? 'Resume illustration' : 'Pause illustration';
    document.querySelectorAll('.orbital-a,.orbital-b').forEach(function (ring) {
      ring.style.animationPlayState = !manualPause && heroVisible && !motion.matches ? 'running' : 'paused';
    });
  }
  motionButton.addEventListener('click', function () { manualPause = !manualPause; updateMotion(); });
  motion.addEventListener('change', updateMotion);
  desktop.addEventListener('change', updateMotion);
  updateMotion();
  var steps = Array.from(document.querySelectorAll('[data-step]'));
  var number = document.getElementById('stageNum');
  var scheduled = false;
  function setMenu(open, restoreFocus) {
    mobile.hidden = !open;
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    if (restoreFocus) menu.focus();
  }
  menu.addEventListener('click', function () { setMenu(mobile.hidden); });
  mobile.querySelectorAll('a').forEach(function (link) {
    link.addEventListener('click', function () { setMenu(false); });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !mobile.hidden) setMenu(false, true);
  });
  desktop.addEventListener('change', function () { if (desktop.matches) setMenu(false); });
  function measure() {
    var height = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = (height > 0 ? Math.max(0, Math.min(100, scrollY / height * 100)) : 0) + '%';
    header.classList.toggle('is-scrolled', scrollY > 80);
    if (desktop.matches) {
      var target = innerHeight * 0.45, closest = 0, distance = Infinity;
      steps.forEach(function (element, index) {
        var box = element.getBoundingClientRect();
        var next = Math.abs((box.top + box.bottom) / 2 - target);
        if (next < distance) { distance = next; closest = index; }
      });
      steps.forEach(function (element, index) { element.classList.toggle('is-active', index === closest); });
      number.textContent = ('0' + (closest + 1)).slice(-2);
    }
    scheduled = false;
  }
  function schedule() { if (!scheduled) { scheduled = true; requestAnimationFrame(measure); } }
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule, { passive: true });
  motion.addEventListener('change', schedule);
  measure();
  document.querySelector('.underline-draw').classList.add('drawn');
  if ('IntersectionObserver' in window) {
    var navigation = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        document.querySelectorAll('.desktop-nav a').forEach(function (link) {
          if (link.getAttribute('href') === '#' + entry.target.id) link.setAttribute('aria-current', 'location');
          else link.removeAttribute('aria-current');
        });
      });
    }, { rootMargin: '-20% 0px -55% 0px' });
    document.querySelectorAll('#approach,#method,#explore,#availability,#questions').forEach(function (section) { navigation.observe(section); });
    var visibility = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        heroVisible = entry.isIntersecting;
        updateMotion();
      });
    });
    visibility.observe(hero);
  }
  var examples = [
    { input: 'ledger add --label "Moss"', result: 'created: 001', question: 'Does every valid label create a new record?', status: 'One observation. Multiple possible rules.' },
    { input: 'ledger add --label "moss"', result: 'duplicate_label', question: 'Are labels compared without case sensitivity?', status: 'A hypothesis worth challenging.' },
    { input: 'ledger remove --id 999', result: 'not_found', question: 'Does the response depend on earlier state?', status: 'Stateful behavior needs a sequence test.' }
  ];
  var choices = Array.from(document.querySelectorAll('[data-case]'));
  function select(index) {
    choices.forEach(function (button, item) {
      button.classList.toggle('selected', index === item);
      button.setAttribute('aria-pressed', String(index === item));
    });
    document.getElementById('caseInput').textContent = examples[index].input;
    document.getElementById('caseResult').textContent = examples[index].result;
    document.getElementById('caseQuestion').textContent = examples[index].question;
    document.getElementById('caseStatus').textContent = examples[index].status;
  }
  choices.forEach(function (button) {
    button.addEventListener('click', function () { select(Number(button.dataset.case)); });
  });
  select(0);
})();
