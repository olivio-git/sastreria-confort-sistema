document.addEventListener('DOMContentLoaded', function() {
    const tipoPrendaSelect = document.querySelector('#id_tipo_prenda');
    const otroPrendaContainer = document.querySelector('#otro_prenda_container');
    const otroPrendaInput = document.querySelector('#id_otro_prenda');
    const tipoReparacionSelect = document.querySelector('#id_tipo_reparacion');
    const otroReparacionContainer = document.querySelector('#otro_reparacion_container');
    const otroReparacionInput = document.querySelector('#id_otro_reparacion');

    if (!tipoPrendaSelect || !tipoReparacionSelect) return;

    function toggleOtroPrenda() {
        const isOtro = tipoPrendaSelect.value === 'otro';
        otroPrendaContainer.style.display = isOtro ? 'block' : 'none';
        if (!isOtro && otroPrendaInput) otroPrendaInput.value = '';
    }

    function toggleOtroReparacion() {
        const isOtro = tipoReparacionSelect.value === 'otro';
        otroReparacionContainer.style.display = isOtro ? 'block' : 'none';
        if (!isOtro && otroReparacionInput) otroReparacionInput.value = '';
    }

    tipoPrendaSelect.addEventListener('change', toggleOtroPrenda);
    tipoReparacionSelect.addEventListener('change', toggleOtroReparacion);

    toggleOtroPrenda();
    toggleOtroReparacion();
});