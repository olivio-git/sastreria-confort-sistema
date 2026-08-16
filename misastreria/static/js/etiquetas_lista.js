(function () {
  'use strict';

  const origen = document.getElementById('nueva-origen');
  const tamano = document.getElementById('nueva-tamano');
  if (!origen || !tamano) return;

  origen.addEventListener('change', () => {
    if (origen.value !== 'textil') return;
    tamano.value = '100x50';
    const vertical = document.querySelector('[name="orientacion"][value="vertical"]');
    if (vertical) vertical.checked = true;
  });
})();
