(function() {
  var PASS = 'Preview';
  var gate = document.getElementById('password-gate');
  if (!gate) return;

  if (sessionStorage.getItem('cc-auth') === 'ok') {
    gate.style.display = 'none';
    document.documentElement.classList.remove('gated');
    return;
  }

  var input = document.getElementById('gate-password');
  var btn = document.getElementById('gate-submit');
  var err = document.getElementById('gate-error');

  function tryAuth() {
    if (input.value === PASS) {
      sessionStorage.setItem('cc-auth', 'ok');
      gate.style.display = 'none';
      document.documentElement.classList.remove('gated');
    } else {
      err.hidden = false;
      input.value = '';
      input.focus();
    }
  }

  btn.addEventListener('click', tryAuth);
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') tryAuth();
  });
})();
