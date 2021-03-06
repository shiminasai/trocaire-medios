# -*- coding: utf-8 -*-
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.http import HttpResponse, HttpResponseRedirect
from django.db.models import get_model, Sum, Q, Max, Min, Avg, Count
from django.utils import simplejson
from django.template.defaultfilters import slugify

#importaciones de los models
from forms import ConsultarForm, MapaForm
from trocaire.medios.templatetags.tools import *
from trocaire.medios.models import *
from trocaire.familia.models import *
from trocaire.participacion_ciudadana.models import *
from trocaire.crisis_alimentaria.models import *
from trocaire.tecnologia.models import *
from trocaire.lugar.models import *
from trocaire.ingresos.models import *
from trocaire.produccion.models import *
from trocaire.formas_propiedad.models import *
from trocaire.genero.models import *
import copy


def _queryset_filtrado_mapa(request):
    '''metodo para obtener el queryset de encuesta
    segun los filtros del formulario que son pasados
    por la variable de sesion'''
    #anio = int(request.session['fecha'])
    #diccionario de parametros del queryset
    params = {}
    if 'fecha1' in request.session:
        params['fecha'] = request.session['fecha1']

    unvalid_keys = []
    for key in params:
        if not params[key]:
            unvalid_keys.append(key)

    for key in unvalid_keys:
        del params[key]

    return Encuesta.objects.filter(**params)


def _query_set_filtrado(request):
    params = {}
    if 'fecha' in request.session:
        params['fecha__in'] = request.session['fecha']

    if request.session['contraparte']:
        params['contraparte__in'] = request.session['contraparte']

    if request.session['departamento']:
        if request.session['municipio']:
            if request.session['comarca']:
                params['comarca'] = request.session['comarca']
            else:
                params['municipio'] = request.session['municipio']
        else:
            params['municipio__departamento'] = request.session['departamento']

    #validando filtro de dependencia familiar
    try:
        if request.session['indice_dep']:
            indice = request.session['indice_dep']

            if indice == u'1':
                params['composicion__dependientes__lt'] = 0.1
            elif indice == u'2':
                params['composicion__dependientes__range'] = (0.1, 1.0)
            elif indice == u'3':
                params['composicion__dependientes__range'] = (1.1, 2.0)
            elif indice == u'4':
                params['composicion__dependientes__range'] = (2.1, 3.0)
            elif indice == u'5':
                params['composicion__dependientes__gt'] = 3.0
    except:
        pass

    #validando acceso a credito
    try:
        if request.session['credito_acceso'] != 'None':
            params['credito'] = request.session['credito_acceso']
    except:
        pass

    unvalid_keys = []
    for key in params:
        if not params[key]:
            #print params[key]
            unvalid_keys.append(key)

    for key in unvalid_keys:
        del params[key]

    #despelote
    encuestas_id = []
    reducir = False
    last_key = (None, None)

    for i, key in enumerate(request.session['parametros']):
        #TODO: REVISAR ESTO
        for k, v in request.session['parametros'][key].items():
            if v is None or str(v) == 'None':
                del request.session['parametros'][key][k]
        model = get_model(*key.split('.'))
        if len(request.session['parametros'][key]):
            reducir = True if (last_key[1] != key > 1 and last_key[0] == None) or reducir==True else False
            last_key = (i, key)
            ids = model.objects.filter(**request.session['parametros'][key]).values_list('encuesta__id', flat=True)
            encuestas_id += ids

    c_flag = params.get('contraparte', None) # flag para saber si se selecciono un contraparte con fin
    # de exluir a ADDAC Rancho Grande de la consulta general -> el jefe manda :P

    if not encuestas_id:
        qs = Encuesta.objects.filter(**params)

        # excluyendo a Rancho Grande a pedido de Boss XD
        if c_flag == None:
            return qs.exclude(municipio__nombre='Rancho Grande')
        return qs
    else:
        ids_definitivos = reducir_lista(encuestas_id) if reducir else encuestas_id
        qs = Encuesta.objects.filter(id__in = ids_definitivos, **params)
        #excluyendo a Rancho Grande
        if c_flag == None:
            return qs.exclude(municipio__nombre='Rancho Grande')
        return qs

def reducir_lista(lista):
    '''reduce la lista dejando solo los elementos que son repetidos
       osea lo contraron a unique'''
    nueva_lista = []
    for foo in lista:
        if lista.count(foo) >= 1 and foo not in nueva_lista:
            nueva_lista.append(foo)
    return nueva_lista

#===============================================================================
def consultar(request):
    if request.method == 'POST':
        form = ConsultarForm(request.POST)
        if form.is_valid():
            request.session['fecha'] = form.cleaned_data['fecha']
            request.session['departamento'] = form.cleaned_data['departamento']
            request.session['contraparte'] = form.cleaned_data['contraparte']
            try:
                municipio = Municipio.objects.get(id=form.cleaned_data['municipio'])
            except:
                municipio = None
            try:
                comarca = Comarca.objects.get(id=form.cleaned_data['comarca'])
            except:
                comarca = None

            request.session['municipio'] = municipio
            request.session['comarca'] = comarca

            #indice de dependencia
            request.session['indice_dep'] = form.cleaned_data['indice_dep']

            #acceso a credito
            request.session['credito_acceso'] = form.cleaned_data['credito_acceso']

            #cosas de otros modelos!
            parametros = {'familia.escolaridad': {}, 'familia.composicion': {},
                          'genero.tomadecicion': {}, 'ingresos.principalesfuentes': {},
                          'ingresos.totalingreso': {}}
            parametros['familia.escolaridad']['beneficia'] = form.cleaned_data['escolaridad_beneficiario']
            parametros['familia.escolaridad']['conyugue'] = form.cleaned_data['escolaridad_conyugue']
            parametros['familia.composicion']['sexo'] = form.cleaned_data['familia_beneficiario']

            #algunos fixes para filtros multipresente
            if form.cleaned_data['familia_beneficiario']:
                request.session['familia_beneficiario'] = form.cleaned_data['familia_beneficiario']

            if form.cleaned_data['escolaridad_beneficiario']:
                request.session['escolaridad_beneficiario'] = form.cleaned_data['escolaridad_beneficiario']

            if form.cleaned_data['escolaridad_conyugue']:
                request.session['escolaridad_conyugue'] = form.cleaned_data['escolaridad_conyugue']

            #desicion gasto mayor!
            #parametros['genero.tomadecicion']['aspectos'] = 1
            parametros['genero.tomadecicion']['respuesta'] =  form.cleaned_data['desicion_gasto_mayor']
            #ingresos
            parametros['ingresos.principalesfuentes']['fuente'] = form.cleaned_data['ingresos_fuente']#TODO: cambiarlo a fuente__in
            parametros['ingresos.totalingreso']['total__gte'] = form.cleaned_data['ingresos_total_min']
            parametros['ingresos.totalingreso']['total__lte'] = form.cleaned_data['ingresos_total_max']

            #parametros['formas_propiedad.finca']['area'] = forms.cleaned_data['finca_area_total']
            #parametros['produccion.ganadomayor']['num_vacas'] = forms.cleaned_data['finca_num_vacas']
            #parametros['finca']['conssa'] = forms.cleaned_data['finca_conssa']
            #parametros['finca']['num_productos'] = forms.cleaned_data['finca_num']
            request.session['parametros'] = parametros

            #encuestas = _query_set_filtrado(request)

            if form.cleaned_data['next_url']:
                return HttpResponseRedirect(form.cleaned_data['next_url'])
            else:
                muestra_indicador = 1
                return render_to_response('encuestas/consultar.html', locals(),
                            context_instance=RequestContext(request))
    else:
        #reset session parameters
        reset_parameters(request)
        form = ConsultarForm()
    return render_to_response('encuestas/consultar.html', locals(),
                              context_instance=RequestContext(request))

def consultarsimple(request):
    if request.method == 'POST':
        form = ConsultarForm(request.POST)
        if form.is_valid():
            request.session['fecha'] = form.cleaned_data['fecha']
            request.session['departamento'] = form.cleaned_data['departamento']
            request.session['contraparte'] = form.cleaned_data['contraparte']
            try:
                municipio = Municipio.objects.get(id=form.cleaned_data['municipio'])
            except:
                municipio = None
            try:
                comarca = Comarca.objects.get(id=form.cleaned_data['comarca'])
            except:
                comarca = None

            request.session['municipio'] = municipio
            request.session['comarca'] = comarca

            #cosas de otros modelos!
            parametros = {'familia.escolaridad': {}, 'familia.composicion': {},
                          'genero.tomadecicion': {}, 'ingresos.principalesfuentes': {},
                          'ingresos.totalingreso': {}}
            parametros['familia.escolaridad']['beneficia'] = form.cleaned_data['escolaridad_beneficiario']
            parametros['familia.escolaridad']['conyugue'] = form.cleaned_data['escolaridad_conyugue']
            parametros['familia.composicion']['sexo'] = form.cleaned_data['familia_beneficiario']

            #desicion gasto mayor!
            parametros['genero.tomadecicion']['respuesta'] =  form.cleaned_data['desicion_gasto_mayor']
            #ingresos
            parametros['ingresos.principalesfuentes']['fuente'] = form.cleaned_data['ingresos_fuente']#TODO: cambiarlo a fuente__in
            parametros['ingresos.totalingreso']['total__gte'] = form.cleaned_data['ingresos_total_min']
            parametros['ingresos.totalingreso']['total__lte'] = form.cleaned_data['ingresos_total_max']

            #parametros['formas_propiedad.finca']['area'] = forms.cleaned_data['finca_area_total']
            #parametros['produccion.ganadomayor']['num_vacas'] = forms.cleaned_data['finca_num_vacas']
            #parametros['finca']['conssa'] = forms.cleaned_data['finca_conssa']
            #parametros['finca']['num_productos'] = forms.cleaned_data['finca_num']
            request.session['parametros'] = parametros

            if form.cleaned_data['next_url']:
                return HttpResponseRedirect(form.cleaned_data['next_url'])
            else:
                muestra_indicador = 1
                return render_to_response('encuestas/consultarsimple.html', locals(),
                            context_instance=RequestContext(request))
    else:
        reset_parameters(request)
        form = ConsultarForm()
    return render_to_response('encuestas/consultarsimple.html', locals(),
                              context_instance=RequestContext(request))

def reset_parameters(request):
    request.session['departamento'] = request.session['municipio'] = request.session['contraparte'] = \
    request.session['comarca'] = request.session['indice_dep'] = request.session['credito_acceso'] = None

    #print 'filters cleaned! :D'

#===============================================================================

def index(request, template_name="index.html"):
    years = []
    for en in Encuesta.objects.order_by('fecha').values_list('fecha', flat=True):
        years.append((en, en))

    fechas_anuales = list(sorted(set(years)))

    agua_segura = {}
    riegos = {}
    ingresos = {}
    conservacion_csa = {}
    for obj in fechas_anuales:
        total_encuesta = Encuesta.objects.filter(fecha=obj[0]).count()

        total_1 = Encuesta.objects.filter(fecha=obj[0], agua__calidad=1,agua__clorada=3).count()
        total_2 = Encuesta.objects.filter(fecha=obj[0], agua__calidad__in=[2,3],agua__clorada=1).count()
        total = total_1 + total_2
        porcentaje_total = round((float(total)/float(total_encuesta))*100,2)

        hombre_1 = Encuesta.objects.filter(fecha=obj[0], sexo_jefe=1, agua__calidad=1,agua__clorada=3).count()
        hombre_2 = Encuesta.objects.filter(fecha=obj[0], sexo_jefe=1, agua__calidad__in=[2,3],agua__clorada=1).count()
        total_hombre = hombre_1 + hombre_2
        porcentaje_hombre = round((float(total_hombre)/float(total_encuesta))*100,2)

        mujer_1 = Encuesta.objects.filter(fecha=obj[0], sexo_jefe=2, agua__calidad=1,agua__clorada=3).count()
        mujer_2 = Encuesta.objects.filter(fecha=obj[0], sexo_jefe=2, agua__calidad__in=[2,3],agua__clorada=1).count()
        total_mujer = mujer_1 + mujer_2
        porcentaje_mujer = round((float(total_mujer)/float(total_encuesta))*100,2)

        agua_segura[obj[1]] = (porcentaje_total,porcentaje_hombre,porcentaje_mujer)

        riego_no_tiene = Encuesta.objects.filter(fecha=obj[0], riego__respuesta=1).count()
        riego_aspercion = Encuesta.objects.filter(fecha=obj[0], riego__respuesta=2).count()
        riego_goteo = Encuesta.objects.filter(fecha=obj[0], riego__respuesta=3).count()
        riego_gravedad = Encuesta.objects.filter(fecha=obj[0], riego__respuesta=4).count()

        #riegos[obj[1]] = (riego_no_tiene,riego_aspercion,riego_goteo,riego_gravedad)

        riegos[obj[1]] = (round(float(riego_no_tiene)/float(total_encuesta)*100,2),
                       round(float(riego_aspercion)/float(total_encuesta)*100,2),
                       round(float(riego_goteo)/float(total_encuesta)*100,2),
                       round(float(riego_gravedad)/float(total_encuesta)*100,2)
                       )

        ingreso_hombre_jefe = TotalIngreso.objects.filter(encuesta__fecha=obj[0],encuesta__sexo_jefe=1).values_list('total', flat=True)
        ingreso_mujer_jefe = TotalIngreso.objects.filter(encuesta__fecha=obj[0],encuesta__sexo_jefe=2).values_list('total', flat=True)

        ingresos[obj[1]] = (calcular_promedio(ingreso_hombre_jefe),
                            calcular_promedio(ingreso_mujer_jefe),
                            )

        csa_si_hombre = para_sacar_csa(request,1,obj[0])
        csa_si_mujer = para_sacar_csa(request,2,obj[0])

        csa_si_total = len(csa_si_hombre) + len(csa_si_mujer)

        csa_no_total = total_encuesta - csa_si_total

        conservacion_csa[obj[1]] = (saca_porcentajes(csa_si_total,total_encuesta,formato=True),
            saca_porcentajes(csa_no_total,total_encuesta,formato=True))


    return render_to_response(template_name, locals(),
                              context_instance=RequestContext(request))

def para_sacar_csa(request,sexo,year):

    lista = []
    for x in Encuesta.objects.filter(sexo_jefe=sexo,fecha=year):
        query = AreaProtegida.objects.filter(encuesta=x, respuesta__in=[2,3,4,5]).aggregate(query=Sum('cantidad'))['query']
        if query > 0:
            lista.append(x.id)

    return lista

def ver_mapita(request, template_name="mapa.html"):
    #familias = Encuesta.objects.all().count()
    if request.method == 'POST':
        form = MapaForm(request.POST)
        if form.is_valid():
            request.session['fecha1'] = form.cleaned_data['fecha1']
    else:
        form = MapaForm()
    return render_to_response(template_name, locals(),
                               context_instance=RequestContext(request))

#FUNCIONES UTILITARIAS PARA TODO EL SITIO
def get_municipios(request, departamento):
    municipios = Municipio.objects.filter(departamento = departamento)
    lista = [(municipio.id, municipio.nombre) for municipio in municipios]
    return HttpResponse(simplejson.dumps(lista), mimetype='application/javascript')

def get_comarca(request, municipio):
    comarcas = Comarca.objects.filter(municipio = municipio)
    lista = [(comarca.id, comarca.nombre) for comarca in comarcas]
    return HttpResponse(simplejson.dumps(lista), mimetype='application/javascript')

def indicadores(request):
    return render_to_response('encuestas/indicadores.html',
                              context_instance=RequestContext(request))

#========================= Salidas sencillas ==================================
def datos_sexo(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    composicion_familia = Composicion.objects.filter(encuesta__id__in=encuestas)
    '''1: Hombre, 2: Mujer'''
    tabla_sexo_jefe = {1: 0, 2: 0}
    tabla_sexo_beneficiario = {}
    tabla_sexo_jefe[1] = encuestas.filter(sexo_jefe=1).count()
    tabla_sexo_jefe[2] = encuestas.filter(sexo_jefe=2).count()
    tabla_sexo_beneficiario['masculino'] = composicion_familia.filter(sexo=1).count()
    tabla_sexo_beneficiario['femenino'] = composicion_familia.filter(sexo=2).count()
    dondetoy = "sexojefe"
    return render_to_response('encuestas/datos_sexo.html', RequestContext(request, locals()))

def comelon(request,hembra,macho):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()

    clorada = []
    total = 0
    for cloro in CHOICE_CALIDAD:
        count_men = encuestas.filter(sexo_jefe=macho,agua__calidad=cloro[0]).count()
        per_men = round(saca_porcentajes(count_men,hombre_jefes),0)
        count_woman = encuestas.filter(sexo_jefe=hembra,agua__calidad=cloro[0]).count()
        per_woman = round(saca_porcentajes(count_woman,mujer_jefes),0)
        total = count_men + count_woman
        clorada.append([cloro[1],count_men,per_men,count_woman,per_woman,total])

    return clorada

def mano_quebrada(request,hembra,macho):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()

    tratamiento = []
    total1 = 0
    for trata in CHOICE_CLORADA:
        count_men = encuestas.filter(sexo_jefe=macho,agua__clorada=trata[0]).count()
        per_men = round(saca_porcentajes(count_men,hombre_jefes),0)
        count_woman = encuestas.filter(sexo_jefe=hembra,agua__clorada=trata[0]).count()
        per_woman = round(saca_porcentajes(count_woman,mujer_jefes),0)
        total1 = count_men + count_woman
        tratamiento.append([trata[1],count_men,per_men,count_woman,per_woman,total1])

    return tratamiento
def agua_clorada(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    numero = encuestas.count()

    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()

    helmy = comelon(request,2,1)
    giacoman = mano_quebrada(request,2,1)
    consolidado = []
    varon= helmy[0][1] + giacoman[0][1]
    por_varon = helmy[0][2] + giacoman[0][2]
    mujer= helmy[0][3] + giacoman[0][3]
    por_mujer = helmy[0][4] + giacoman[0][4]
    total= helmy[0][5] + giacoman[0][5]
    try:
        por_total = round(float(total)/float(numero)*100,2)
    except:
        por_total = 0.0

    dondetoy = "cloran"
    return render_to_response('encuestas/agua_clorada.html', RequestContext(request,locals()))

def gastan_horas(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    numero = encuestas.count()
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()
    #salidas cuantas horas gastan
    tablas_gastan = {}

    tablas_gastan['masculino'] = encuestas.filter(sexo_jefe=1, agua__tiempo=3).count()
    tablas_gastan['porcentaje_masculino'] = round(saca_porcentajes(tablas_gastan['masculino'],hombre_jefes),1)

    tablas_gastan['femenino'] = encuestas.filter(sexo_jefe=2, agua__tiempo=3).count()
    tablas_gastan['porcentaje_femenino'] = round(saca_porcentajes(tablas_gastan['femenino'],mujer_jefes),1)

    tablas_gastan['total'] =  tablas_gastan['masculino'] + tablas_gastan['femenino']
    tablas_gastan['porcentaje_total'] = round(saca_porcentajes(tablas_gastan['total'],numero),1)
    dondetoy = "recolectar"
    return render_to_response('encuestas/gastan_horas.html', RequestContext(request,locals()))

def manzana(request,sexo):
    encuestas = _query_set_filtrado(request)

    lista = []
    for x in encuestas.filter(sexo_jefe=sexo):
        query = AreaProtegida.objects.filter(encuesta=x, respuesta__in=[2,3,4,5]).aggregate(query=Sum('cantidad'))['query']
        if query > 0:
            lista.append(x.id)

    return lista

def manzana2(request,sexo):
    encuestas = _query_set_filtrado(request)

    lista = []
    for x in encuestas.filter(sexo_jefe=sexo):
        query = AreaProtegida.objects.filter(encuesta=x, respuesta__in=[2,3,4,5]).aggregate(query=Sum('cantidad'))['query']
        if query > 0:
            lista.append(query)

    return lista

def familias_practicas(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)

    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes =  encuestas.filter(sexo_jefe=2).count()

    conservacion_h = manzana(request,1)
    conservacion_m = manzana(request,2)
    total = len(encuestas)

    hombre = len(conservacion_h)
    por_hombre = round(saca_porcentajes(hombre,hombre_jefes),1)
    area_hombre = manzana2(request, 1)
    csa_total_h = 0
    for suma in area_hombre:
        csa_total_h += suma

    mujer = len(conservacion_m)
    por_mujer = round(saca_porcentajes(mujer,mujer_jefes),1)
    area_mujer = manzana2(request, 2)
    csa_total_m = 0
    for suma in area_mujer:
        csa_total_m += suma

    total_h_m = hombre + mujer
    por_total_h_m = round(saca_porcentajes(total_h_m,total),1)
    area_total = csa_total_h + csa_total_m #Esta es area de CSA

    no_total = total - total_h_m
    por_no_total = round(saca_porcentajes(no_total,total),1)
    no_hombre = hombre_jefes - hombre
    por_no_hombre = round(saca_porcentajes(no_hombre,hombre_jefes),1)
    no_mujer = mujer_jefes - mujer
    por_no_mujer = round(saca_porcentajes(no_mujer,mujer_jefes),1)
    dondetoy = "conservacion"
    return render_to_response('encuestas/familias_practicas.html', RequestContext(request,locals()))

def rango_mz(request,sexo):
    encuestas = _query_set_filtrado(request)
    lista = []
    for x in encuestas.filter(sexo_jefe=sexo):
        query = Tierra.objects.filter(encuesta=x, area=1).aggregate(mujer=Sum('mujer'),
                                                            hombre=Sum('hombre'),
                                                            ambos=Sum('ambos'))
        lista.append([x.id,query])
    return lista

def acceso_tierra(request):
    encuestas = _query_set_filtrado(request)
    numero = encuestas.count()
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()

    #salidas cuantas horas gastan
    dicc1 = {}
    dicc1_h_m = {}
    for a in CHOICE_AREA[1:5]:
        total = Tierra.objects.filter(area=a[0], encuesta__in=encuestas)
        dicc1[a[1]] = total.count()
        dicc1_h_m[a[1]] = _hombre_mujer_dicc(total.values_list('encuesta__id', flat=True))
    tabla_dicc1 = _order_dicc(copy.deepcopy(dicc1))

    #-------------- start clean code XD ---------------------
    '''rangos: 1 => 0, 2 => 0.1 a 1 mz, 3 => 1.1 a 5 mz, 4 => 5.1 a 10 mz, 5 => mas de 10 mz'''

    labels = {1: '0 mz', 2: '0.1 - 0.3 mz', 3: '0.31 - 1 mz', 4: '1.1 - 5 mz', 5: '5.1 - 10 mz', 6: 'más de 10 mz'}
    query = Tierra.objects.filter(encuesta__in=encuestas, area=1)
    total_all = query.count()
    total_hombre = query.filter(encuesta__sexo_jefe=1).count()
    total_mujer = query.filter(encuesta__sexo_jefe=2).count()

    dicc = area_total_rangos(query)
    dicc_hombre = area_total_rangos(query.filter(encuesta__sexo_jefe=1))
    dicc_mujer = area_total_rangos(query.filter(encuesta__sexo_jefe=2))

    try:
        promedio_mz = round(query.aggregate(promedio=Avg('area_total'))['promedio'], 2)
    except:
        pass
    suma = 0
    for obj in dicc.items():
        if obj[0] > 3:
            suma += obj[1]

    try:
        porcentaje = round(float(suma)/float(total_all) * 100,2)
    except:
        pass

    dondetoy = "accesotierra"
    return render_to_response('encuestas/acceso_tierra.html', RequestContext(request,locals()))

def area_total_rangos(query):
    return {1: query.filter(area_total=0.0).count(),
            2: query.filter(area_total__range=(0.1, 0.3)).count(),
            3: query.filter(area_total__range=(0.31, 1.0)).count(),
            4: query.filter(area_total__range=(1.1, 5.0)).count(),
            5: query.filter(area_total__range=(5.1, 10.0)).count(),
            6: query.filter(area_total__gt=10.0).count()}

def riego(request,sexo,tipo):
    encuestas = _query_set_filtrado(request)

    lista = []
    suma = 0
    for x in encuestas.filter(sexo_jefe=sexo):
        query = Riego.objects.filter(encuesta=x, respuesta__in=[tipo]).aggregate(query=Sum('area'))['query']
        if query > 0:
            suma += query
            lista.append([x.id,suma])
    return lista

def acceso_agua(request):
    encuestas = _query_set_filtrado(request)
    numero = encuestas.count()
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()
    #hombre acceso a agua para riego
    lista_a_h = riego(request,1,2)
    aspersion_h = len(lista_a_h)
    try:
        total_lista_a_h = lista_a_h[(len(lista_a_h))-1][1]
    except:
        total_lista_a_h = 0
    #-----------------------------
    lista_g_h = riego(request,1,3)
    goteo_h = len(lista_g_h)
    try:
        total_lista_g_h = lista_g_h[(len(lista_g_h))-1][1]
    except:
        total_lista_g_h = 0
    #-----------------------------
    lista_gra_h = riego(request,1,4)
    gravedad_h = len(lista_gra_h)
    try:
        total_lista_gra_h = lista_gra_h[(len(lista_gra_h))-1][1]
    except:
        total_lista_gra_h = 0
    #-------------------------------
    lista_o_h = riego(request,1,5)
    otro_h = len(lista_o_h)
    try:
        total_o_h = lista_o_h[(len(lista_o_h))-1][1]
    except:
        total_o_h = 0

    #mujer acceso a agua para riego
    lista_a_m = riego(request,2,2)
    aspersion_m = len(lista_a_m)
    try:
        total_lista_a_m = lista_a_m[(len(lista_a_m))-1][1]
    except:
        total_lista_a_m = 0
    #----------------------------
    lista_g_m = riego(request,2,3)
    goteo_m = len(lista_g_m)
    try:
        total_lista_g_m = lista_g_m[(len(lista_g_m))-1][1]
    except:
        total_lista_g_m = 0
    #-----------------------------
    lista_gra_m = riego(request,2,4)
    gravedad_m = len(lista_gra_m)
    try:
        total_lista_gra_m = lista_gra_m[(len(lista_gra_m))-1][1]
    except:
        total_lista_gra_m = 0
    #-------------------------------
    lista_o_m = riego(request,1,5)
    otro_m = len(lista_o_m)
    try:
        total_o_m = lista_o_m[(len(lista_o_m))-1][1]
    except:
        total_o_m = 0
    #total de conteo
    total_aspersion = aspersion_h + aspersion_m
    total_goteo = goteo_h + goteo_m
    total_gravedad = gravedad_h + gravedad_m
    total_otros = otro_h + otro_m

    #calculo de los que no tienen riego
    no_tiene_riego = numero - (total_aspersion + total_goteo + total_gravedad + total_otros)

    #total de manzanas
    total_manzadas_aspersion = total_lista_a_h + total_lista_a_m
    total_manzadas_goteo = total_lista_g_h + total_lista_g_m
    total_manzanas_gravedad = total_lista_gra_h + total_lista_gra_m
    total_manzanas_otros = total_o_h + total_o_m

    gran_total = total_aspersion + total_goteo + total_gravedad
    por_gran_total = round(float(gran_total)/float(numero)*100,2)
    mujer_total = aspersion_m + goteo_m + gravedad_m
    por_mujer_total = round(float(mujer_total)/float(mujer_jefes)*100,2)
    hombre_total = aspersion_h + goteo_h + gravedad_h
    por_hombre_total = round(float(hombre_total)/float(hombre_jefes)*100,2)



    dondetoy = "accesoagua"
    return render_to_response('encuestas/acceso_agua.html', RequestContext(request,locals()))

def reponsable(request,sexo):
    encuestas = _query_set_filtrado(request)

    lista = {}
    for hombre in CHOICE_GENERO:
        conteo = Genero.objects.filter(encuesta__in=encuestas, encuesta__sexo_jefe=sexo,
                                       responsabilidades=hombre[0]).count()
        lista[hombre[1]] = conteo
    lista2 = _order_dicc(copy.deepcopy(lista))
    return lista2

def dependencia(request):
    encuestas = _query_set_filtrado(request)
    query = Composicion.objects.filter(encuesta__in=encuestas)
    query_hombre_jefe = query.filter(encuesta__sexo_jefe=1)
    query_mujer_jefe = query.filter(encuesta__sexo_jefe=2)

    tabla = vale_gaver(query)
    tabla_hombre = vale_gaver(query_hombre_jefe)
    tabla_mujer = vale_gaver(query_mujer_jefe)

    keys = {1: u'Igual a 0'
            , 2: u'De 0.1 a 1.0'
            , 3: u'De 1.1 a 2.0'
            , 4: u'De 2.1 a 3.0'
            , 5: u'Más de 3.0'}

    dondetoy = "dependencia"
    return render_to_response('encuestas/dependencia.html', RequestContext(request, locals()))

def vale_gaver(query):
    return {u'Igual a 0': query.filter(dependientes__lte=0).count(),
             u'De 0.1 a 1.0': query.filter(dependientes__range=(0.1, 1.0)).count(),
             u'De 1.1 a 2.0': query.filter(dependientes__range=(1.1, 2.0)).count(),
             u'De 2.1 a 3.0': query.filter(dependientes__range=(2.1, 3.0)).count(),
             u'Más de 3.0': query.filter(dependientes__gt=3.0).count()}

def sueno_tengo(request, numero):
    encuestas = _query_set_filtrado(request)
    dicc2 = {}
    for filas in CHOICE_GENERO:
        key = slugify(filas[1]).replace('-', '_')
        dicc2[key] = {}
        for resp in CHOICE_GENERO_RESPUESTA:
            key2 = slugify(resp[1]).replace('-', '_')
            dicc2[key][key2] = conteo = encuestas.filter(sexo_jefe=numero,genero__responsabilidades=filas[0],genero__respuesta=resp[0]).count()

    return dicc2


def hombre_responsable(request):
    encuestas = _query_set_filtrado(request)
    numero = encuestas.count()
    hombre_jefes = encuestas.filter(sexo_jefe=1).count()
    mujer_jefes = encuestas.filter(sexo_jefe=2).count()

    carlos = sueno_tengo(request,1)
    lava = total_dict(carlos[u'152_lava_y_plancha'])
    cocina = total_dict(carlos[u'151_cocina'])
    lleva  = total_dict(carlos[u'150_lleva_sus_hijos_e_hijas_al_centro_de_salud'])
    asiste = total_dict(carlos[u'149_asiste_a_las_reuniones_de_la_escuela'])
    atiende = total_dict(carlos[u'154_atiende_a_sus_hijas_e_hijos'])
    barre = total_dict(carlos[u'153_barre_limpia_la_casa'])

    rocha = sueno_tengo(request,2)
    lava1 = total_dict(rocha[u'152_lava_y_plancha'])
    cocina1 = total_dict(rocha[u'151_cocina'])
    lleva1  = total_dict(rocha[u'150_lleva_sus_hijos_e_hijas_al_centro_de_salud'])
    asiste1 = total_dict(rocha[u'149_asiste_a_las_reuniones_de_la_escuela'])
    atiende1 = total_dict(rocha[u'154_atiende_a_sus_hijas_e_hijos'])
    barre1 = total_dict(rocha[u'153_barre_limpia_la_casa'])


    dondetoy = "hombreresp"
    return render_to_response('encuestas/hombre_responsable.html', RequestContext(request,locals()))

def mujeres_decisiones(request):
    encuestas = _query_set_filtrado(request)
    numero = encuestas.count()
    tabla_mujeres = {}
    key = '% de familias según quien toma las decisiones'
    for a in CHOICE_ASPECTO:
        con_hombre = TomaDecicion.objects.filter(encuesta__in=encuestas, respuesta=1, aspectos=a[0]).count()
        con_mujer = TomaDecicion.objects.filter(encuesta__in=encuestas, respuesta=2, aspectos=a[0]).count()
        con_ambos = TomaDecicion.objects.filter(encuesta__in=encuestas, respuesta=3, aspectos=a[0]).count()
        no_aplica = TomaDecicion.objects.filter(encuesta__in=encuestas, respuesta=4, aspectos=a[0]).count()
        tabla_mujeres[a[1]] = {'hombre':con_hombre,'mujer':con_mujer,
                               'ambos':con_ambos,'no aplica':no_aplica}

    tabla_mu = _order_dicc(copy.deepcopy(tabla_mujeres))
    dondetoy = "mujeresdecision"
    return render_to_response('encuestas/mujeres_decisiones.html', RequestContext(request,locals()))

def sexo_beneficiario(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    '''1: hombre, 2: mujer'''

    query_hombre = Composicion.objects.filter(encuesta__id__in=encuestas.filter(sexo_jefe=1))
    query_mujer = Composicion.objects.filter(encuesta__id__in=encuestas.filter(sexo_jefe=2))

    mujer_jefe = {1:query_mujer.filter(sexo=1).count(), 2:query_mujer.filter(sexo=2).count()}
    hombre_jefe = {1:query_hombre.filter(sexo=1).count(), 2:query_hombre.filter(sexo=2).count()}

    dondetoy = "sexobene"
    return render_to_response('encuestas/sexo_beneficiario.html', RequestContext(request, locals()))

def escolaridad(request):
    encuestas = _query_set_filtrado(request)
    esc_benef = {}
    #escolaridad por hombre y mujer
    esc_h_m = {}
    for nivel_edu in CHOICE_ESCOLARIDAD:
        escolaridad_query = Escolaridad.objects.filter(beneficia=nivel_edu[0], encuesta__in=encuestas)
        esc_benef[nivel_edu[1]] = escolaridad_query.count()
        esc_h_m[nivel_edu[1]] = _hombre_mujer_dicc(escolaridad_query.values_list('encuesta__id', flat=True))
    tabla_esc_benef = _order_dicc(copy.deepcopy(esc_benef))
    dondetoy = "escolaridad"
    return render_to_response('encuestas/escolaridad.html', RequestContext(request, locals()))

###################################################################################

def cuatrocuatro(request):
    encuestas = _query_set_filtrado(request)
    alquilo = {}
    alquilo_h_m = {}

    for alquiler in Ciclo.objects.all():
        nose = Propiedad.objects.filter(ciclo=alquiler, encuesta__in=encuestas)
        alquilo[alquiler] = nose.count()
        alquilo_h_m[alquiler] = _hombre_mujer_dicc(nose.values_list('encuesta__id', flat=True))
    tabla_alquiler = _order_dicc(copy.deepcopy(alquilo))
    dondetoy = "cuatrocuatro"
    return render_to_response('encuestas/cuatro.html', RequestContext(request, locals()))

def cultivos_periodos(request):
    encuestas = _query_set_filtrado(request)
    c_peridos_m = {} #macho
    c_peridos_h = {} #hembra

    for cultivo in CPeriodos.objects.all():
        total_mz = CultivosPeriodos.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosPeriodos.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_peridos_m[cultivo] = [total_mz,total_pr,productividad]

    for cultivo in CPeriodos.objects.all():
        total_mz = CultivosPeriodos.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosPeriodos.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_peridos_h[cultivo] = [total_mz,total_pr,productividad]

    dondetoy = "cperiodos"
    return render_to_response('encuestas/cperiodos.html', RequestContext(request, locals()))

def cultivos_permanentes(request):
    encuestas = _query_set_filtrado(request)
    c_permanente_m = {} #macho
    c_permanente_h = {} #hembra

    for cultivo in CPermanentes.objects.exclude():
        total_mz = CultivosPermanentes.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosPermanentes.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_permanente_m[cultivo] = [total_mz,total_pr,productividad]

    for cultivo in CPermanentes.objects.exclude():
        total_mz = CultivosPermanentes.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosPermanentes.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_permanente_h[cultivo] = [total_mz,total_pr,productividad]
    dondetoy = "cpermanente"
    return render_to_response('encuestas/cpermanentes.html', RequestContext(request, locals()))

def cultivos_anuales(request):
    encuestas = _query_set_filtrado(request)
    c_anuales_m = {} #macho
    c_anuales_h = {} #hembra

    for cultivo in CAnuales.objects.all():
        total_mz = CultivosAnuales.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosAnuales.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=1).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_anuales_m[cultivo] = [total_mz,total_pr,productividad]

    for cultivo in CAnuales.objects.all():
        total_mz = CultivosAnuales.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_mz=Sum('manzana'))['total_mz']
        total_pr = CultivosAnuales.objects.filter(cultivos=cultivo, encuesta__in=encuestas, encuesta__sexo_jefe=2).aggregate(total_pr=Sum('produccion'))['total_pr']
        try:
            productividad = total_pr / total_mz if total_mz != 0 else 0
        except:
            productividad = 0

        c_anuales_h[cultivo] = [total_mz,total_pr,productividad]
    dondetoy = "canuales"
    return render_to_response('encuestas/canuales.html', RequestContext(request, locals()))

def desglose_periodo(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0

    for cultivo in CIPeriodos.objects.all():
        primera = CultivosIPeriodos.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(primera=Sum('total_primera'))['primera']
        postrera = CultivosIPeriodos.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(postrera=Sum('total_postrera'))['postrera']
        apante = CultivosIPeriodos.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(apante=Sum('total_apante'))['apante']
        total = CultivosIPeriodos.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [primera,postrera,apante,total]

    return [dicc,suma]

def desglose_permanentes(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0
    for cultivo in CIPermanentes.objects.all():
        total = CultivosIPermanentes.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]
    return [dicc,suma]

def desglose_estacionales(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0
    for cultivo in CIEstacionales.objects.all():
        total = CultivosIEstacionales.objects.filter(cultivo=cultivo,
                                                   encuesta__in=encuestas,
                                                   encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]
    return [dicc,suma]

def desglose_hortaliza(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0
    for cultivo in CIHortalizas.objects.all():
        total = IHortalizas.objects.filter(hortaliza=cultivo,
                                        encuesta__in=encuestas,
                                        encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]
    return [dicc,suma]

def desglose_patio(request,sexo):
    encuestas = _query_set_filtrado(request)

    total = IngresoPatio.objects.filter(encuesta__in=encuestas,
                                        encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
    if total == None:
        total = 0

    return total

def desglose_ganado(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0
    for cultivo in Ganados.objects.all():
        total = IngresoGanado.objects.filter(ganado=cultivo,
                                        encuesta__in=encuestas,
                                        encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]
    return [dicc,suma]

def desglose_lactios(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0

    for cultivo in Productos.objects.all():
        verano = Lactios.objects.filter(producto=cultivo,
                                    encuesta__in=encuestas,
                                    encuesta__sexo_jefe=sexo).aggregate(verano=Sum('total_verano'))['verano']
        invierno = Lactios.objects.filter(producto=cultivo,
                                    encuesta__in=encuestas,
                                    encuesta__sexo_jefe=sexo).aggregate(invierno=Sum('total_invierno'))['invierno']

        total = Lactios.objects.filter(producto=cultivo,
                                    encuesta__in=encuestas,
                                    encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [verano,invierno,total]

    return [dicc,suma]

def desglose_pproceso(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0

    for cultivo in PProcesado.objects.all():
        total = ProductosProcesado.objects.filter(producto=cultivo,
                                    encuesta__in=encuestas,
                                    encuesta__sexo_jefe=sexo).aggregate(monto=Sum('monto'))['monto']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]

    return [dicc,suma]

def desglose_otroingreso(request,sexo):
    encuestas = _query_set_filtrado(request)

    dicc = {}
    suma = 0

    for cultivo in OtrasActividades.objects.all():
        total = OtrosIngresos.objects.filter(actividad=cultivo,
                                    encuesta__in=encuestas,
                                    encuesta__sexo_jefe=sexo).aggregate(total=Sum('total'))['total']
        try:
            suma += total
        except:
            suma += 0
        dicc[cultivo] = [total]

    return [dicc,suma]


def ingreso_desglosado(request):
    encuestas = _query_set_filtrado(request)
    hombres = encuestas.filter(sexo_jefe=1).count()
    mujeres = encuestas.filter(sexo_jefe=2).count()

    periodo_h = desglose_periodo(request,1) #hombres
    #print periodo_h[1]
    periodo_m = desglose_periodo(request, 2) #mujeres

    permanente_h = desglose_permanentes(request, 1) #hombre
    permanente_m = desglose_permanentes(request, 2) #mujer

    estacionales_h =desglose_estacionales(request, 1)
    estacionales_m =desglose_estacionales(request, 2)

    hortaliza_h = desglose_hortaliza(request, 1)
    hortaliza_m = desglose_hortaliza(request, 2)

    patio_h = desglose_patio(request, 1)
    patio_m = desglose_patio(request, 2)

    ganado_h = desglose_ganado(request, 1)
    ganado_m = desglose_ganado(request, 2)

    lacteos_h = desglose_lactios(request, 1)
    lacteos_m = desglose_lactios(request, 2)

    pproceso_h = desglose_pproceso(request, 1)
    pproceso_m = desglose_pproceso(request, 2)

    otroingreso_h = desglose_otroingreso(request, 1)
    otroingreso_m = desglose_otroingreso(request, 2)

    ingreso_hombres = periodo_h[1] + permanente_h[1] + estacionales_h[1] + \
                      hortaliza_h[1] + patio_h + ganado_h[1] + lacteos_h[1] + \
                      pproceso_h[1]

    ingreso_mujeres = periodo_m[1] + permanente_m[1] + estacionales_m[1] + \
                      hortaliza_m[1] + patio_m + ganado_m[1] + lacteos_m[1] + \
                      pproceso_m[1]

    total_h = ingreso_hombres + otroingreso_h[1]
    total_m = ingreso_mujeres + otroingreso_m[1]

    dondetoy = "desglose"
    return render_to_response('encuestas/ingreso_desglose.html', RequestContext(request, locals()))

#------------------------------------------------------------------------------

def credito(request):
    encuestas = _query_set_filtrado(request)
    opciones = Credito.objects.all().exclude(id__in=[1, 7])
    no_tiene = Credito.objects.get(id=1)
    credito = {}
    credito_h_m = {}
    for op in opciones:
        query = AccesoCredito.objects.filter(Q(hombre=op) | Q(mujer=op), encuesta__in=encuestas)
        credito[op.nombre] = query.count()
        credito_h_m[op.nombre] = {1: query.filter(encuesta__sexo_jefe=1).count(),
                                  2: query.filter(encuesta__sexo_jefe=2).count()}

    query_no_tiene = AccesoCredito.objects.filter(hombre=no_tiene, mujer=no_tiene, encuesta__in=encuestas)
    credito[no_tiene.nombre] = query_no_tiene.count()
    credito_h_m[no_tiene.nombre] = {1: query_no_tiene.filter(encuesta__sexo_jefe=1).count(),
                                  2: query_no_tiene.filter(encuesta__sexo_jefe=2).count()}

    tabla_credito = _order_dicc(copy.deepcopy(credito))

    hombre_jefe = encuestas.filter(sexo_jefe=1).count()
    mujer_jefe = encuestas.filter(sexo_jefe=2).count()
    dondetoy = "creditofamilia"
    return render_to_response('encuestas/credito.html', RequestContext(request, locals()))

def participacion(request):
    encuestas = _query_set_filtrado(request)
    total_general = encuestas.count()
    query_all = ParticipacionCPC.objects.filter(encuesta__in=encuestas)
    part_cpc = get_participacion(query_all, 1)
    part_asam = get_participacion(query_all, 2)

    #-- obtener cuando el jefe de familia es hombre
    query_hombre = ParticipacionCPC.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=1))
    part_cpc_hombre = get_participacion(query_hombre, 1)
    part_asam_hombre = get_participacion(query_hombre, 2)

    #-- obtener cuando el jefe de familia es mujer
    query_mujer = ParticipacionCPC.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=2))
    part_cpc_mujer = get_participacion(query_mujer, 1)
    part_asam_mujer = get_participacion(query_mujer, 2)

    hombre_jefe = encuestas.filter(sexo_jefe=1).count()
    mujer_jefe = encuestas.filter(sexo_jefe=2).count()

    dondetoy = "participacion"
    return render_to_response('encuestas/participacion.html', RequestContext(request, locals()))

def get_participacion(query_param, organismo):
    query = query_param.filter(organismo=organismo)
    dicc = {'hombre': query.filter(hombre__gt=0).count(),
            'mujer': query.filter(mujer__gt=0).count(),
            'ambos': query.filter(ambos__gt=0).count(),
            'total': query.count()}
    return dicc

def ingreso_agropecuario(request):
    encuestas = _query_set_filtrado(request)
    query = TotalIngreso.objects.filter(encuesta__in=encuestas)

    #obtener queries segun jefe de familia
    query_hombre = TotalIngreso.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=1))
    query_mujer = TotalIngreso.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=2))

    ingreso_agropecuario = {'total': query.filter(total_ap__gte=1).count(),
            'hombre': query_hombre.filter(total_ap__gte=1).count(),
            'mujer': query_mujer.filter(total_ap__gte=1).count()}
    dondetoy = "actividadesagro"
    return render_to_response('encuestas/ingreso_agropecuario.html', RequestContext(request, locals()))

def ingreso_familiar(request, agro='total', titulo=None, dondetoy='ingresosfam'):
    encuestas = _query_set_filtrado(request)
    ingresos = TotalIngreso.objects.filter(encuesta__in=encuestas).values_list(agro, flat=True)

    #obtener queries segun jefe de familia
    query_hombre_jefe = TotalIngreso.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=1)).values_list(agro, flat=True)
    query_mujer_jefe = TotalIngreso.objects.filter(encuesta__in=encuestas.filter(sexo_jefe=2)).values_list(agro, flat=True)

    promedio = {'total': calcular_promedio(ingresos),
                'hombre_jefe': calcular_promedio(query_hombre_jefe),
                'mujer_jefe': calcular_promedio(query_mujer_jefe)
                }

    mediana = {'total': calcular_mediana(ingresos),
                'hombre_jefe': calcular_mediana(query_hombre_jefe),
                'mujer_jefe': calcular_mediana(query_mujer_jefe)
                }
    return render_to_response('encuestas/ingreso_familiar.html', RequestContext(request, locals()))

def abastecimiento(request):
    encuestas = _query_set_filtrado(request)
    jefes_ids = _queryid_hombre_mujer(encuestas.values_list('id', flat=True), flag=True)
    frijol = {1: 0, 2: 0}
    maiz = {1: 0, 2: 0}

    encuestas_sin_consumo = []
    encuestas_sin_maiz = []
    encuestas_sin_frijol = []

    for key, lista in {1: encuestas.filter(sexo_jefe=1), 2: encuestas.filter(sexo_jefe=2)}.items():
        for encuesta in lista:
            #total_personas = sum([desc.femenino+desc.masculino for desc in Descripcion.objects.filter(encuesta=encuesta)])
            try:
                consumo_query = ConsumoDiario.objects.get(encuesta=encuesta)
                maiz_query = CultivosPeriodos.objects.get(encuesta=encuesta, cultivos__id=1)
            except ConsumoDiario.DoesNotExist:
                encuestas_sin_consumo.append(encuesta.id)
                continue
            except CultivosPeriodos.DoesNotExist:
                encuestas_sin_maiz.append(encuesta.id)
                continue
            except:
                continue

            try:
                frijol_query = CultivosPeriodos.objects.get(encuesta=encuesta, cultivos__id=3)
            except CultivosPeriodos.DoesNotExist:
                encuestas_sin_frijol.append(encuesta.id)
                continue

            produccion_diaria_maiz = round((maiz_query.produccion*float(100))/float(365), 2)
            produccion_diaria_frijol = round((frijol_query.produccion*float(100))/float(365), 2)
            if consumo_query.maiz <= produccion_diaria_maiz:
                maiz[key] += 1

            if consumo_query.frijol <= produccion_diaria_frijol:
                frijol[key] += 1

    frijol['total'] = sum(frijol.values())
    maiz['total'] = sum(maiz.values())

    totales = {1: len(jefes_ids[1]), 2: len(jefes_ids[2]), 3: len(jefes_ids[3])}
    totales['total'] = sum(totales.values())
    dondetoy = "autoabastecimiento"
    return render_to_response('encuestas/abastecimiento.html', RequestContext(request, locals()))

def diversidad_alimentaria(request):
    titulo = u'Diversidad de la dieta familiar'
    encuestas = _query_set_filtrado(request)
    query_hombre = encuestas.filter(sexo_jefe=1)
    query_mujer = encuestas.filter(sexo_jefe=2)

    dicc = get_diversidad_dicc(encuestas)
    dicc_hombre = get_diversidad_dicc(query_hombre)
    dicc_mujer = get_diversidad_dicc(query_mujer)

    total = total_dict(dicc)
    total_hombre = total_dict(dicc_hombre)
    total_mujer = total_dict(dicc_mujer)

    labels = {1: 'Al menos 1', 2: 'Al menos 2',
              3: 'Al menos 3', 4: 'Al menos 4',
              5: 'Al menos 5', 6: 'Al menos 6',
              7: 'Al menos 7'}
    dondetoy = "diversidad_ali"
    return render_to_response('encuestas/diversidad_alimentaria.html',
                                RequestContext(request, locals()))

def get_diversidad_dicc(query):
    dicc = {1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0}

    #grupos de alimentos
    granos = [1, 2, 3, 4, 5] #maiz, frijol, sorgo y arroz
    feculas = [6, 7, 8, 9] #papas, camote, yuca, malanga
    frutas_verduras = [10, 11, 12, 13] #verduras, hostalizas, frutas
    lacteos = [14, 15] #lacteo y huevos
    carne = [16] #carne
    grasas = [17] #grasas y aceite
    otros = [18, 19, 20]

    for obj in query:
        grupo = 0
        for group in granos, feculas, frutas_verduras, lacteos, carne, grasas, otros:
            if obj.diversidad_set.filter(alimento__id__in=group, respuesta=1).count() != 0:
                grupo += 1

        if grupo != 0:
            dicc[grupo] += 1

    return dicc

def diversificacion_productiva(request):
#    import inspect
#    print "My name is: %s" % inspect.stack()[0][3]
    titulo = u'Diversificación productiva'
    encuestas = _query_set_filtrado(request)
    query_hombre = encuestas.filter(sexo_jefe=1)
    query_mujer = encuestas.filter(sexo_jefe=2)

    dicc = get_div_produc(encuestas)
    dicc_hombre = get_div_produc(query_hombre)
    dicc_mujer = get_div_produc(query_mujer)

    total = total_dict(dicc)
    total_hombre = total_dict(dicc_hombre)
    total_mujer = total_dict(dicc_mujer)

    labels = {0: 'Ninguno', 1: '1 cultivo', 2: '2 cultivos',
              3: '3 cultivos', 4: '4 cultivos',
              5: '5 cultivos', 6: '6 cultivos',
              7: '7 cultivos', 8: '8 cultivos o más'}
    dondetoy = "div_produc"

    return render_to_response('encuestas/diversificacion_productiva.html', RequestContext(request, locals()))

def get_div_produc(query):
    dicc = {0: 0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0, 8:0}
    for obj in query:
        c_periodos = obj.cultivosperiodos_set.filter().count()
        c_permanentes = obj.cultivospermanentes_set.filter().count()
        c_anuales = obj.cultivosanuales_set.filter().count()
        c_hortalizas = obj.hortalizas_set.filter().count()
        cultivos = c_periodos + c_permanentes + c_anuales + c_hortalizas
        if cultivos > 0 and cultivos < 8:
            dicc[cultivos] += 1
        elif cultivos >= 8:
            dicc[8] += 1
        else:
            dicc[cultivos] += 1

    return dicc

def venta_organizada(request):
    encuestas = _query_set_filtrado(request)
    labels = {1: '% de familias que venden', 2: '% de familias que no venden'}
    titulo = u'Acceso de las familias para vender sus productos de forma organizada'
    #datos nuevos pedido ronnie
    nuevo_global = encuestas.count()
    nuevo_hombre = encuestas.filter(sexo_jefe=1).count()
    nuevo_mujer = encuestas.filter(sexo_jefe=2).count()

    filtro = [2, 3, 4]
    venta = get_vende_num(encuestas, filtro)
    venta_hombre = get_vende_num(encuestas.filter(sexo_jefe=1), filtro)
    venta_mujer = get_vende_num(encuestas.filter(sexo_jefe=2), filtro)

    total = sum(venta)
    total_hombre = sum(venta_hombre)
    total_mujer = sum(venta_mujer)

    dicc = {1: venta[0], 2: venta[1]}
    dicc_hombre = {1: venta_hombre[0], 2: venta_hombre[1]}
    dicc_mujer = {1: venta_mujer[0], 2: venta_mujer[1]}
    dondetoy = "venta_org"
    return render_to_response('encuestas/venta_organizada.html', RequestContext(request, locals()))

def familias_venden(request):
    encuestas = _query_set_filtrado(request)
    labels = {1: '% de familias que venden', 2: '% de familias que no venden'}
    titulo = 'Familias que venden sus productos'

    filtro = [1, 2, 3, 4]
    venta = get_vende_num(encuestas, filtro)
    venta_hombre = get_vende_num(encuestas.filter(sexo_jefe=1), filtro)
    venta_mujer = get_vende_num(encuestas.filter(sexo_jefe=2), filtro)

    nuevo_global = encuestas.count()
    nuevo_hombre = encuestas.filter(sexo_jefe=1).count()
    nuevo_mujer = encuestas.filter(sexo_jefe=2).count()

    total = sum(venta)
    total_hombre = sum(venta_hombre)
    total_mujer = sum(venta_mujer)

    dicc = {1: venta[0], 2: venta[1]}
    dicc_hombre = {1: venta_hombre[0], 2: venta_hombre[1]}
    dicc_mujer = {1: venta_mujer[0], 2: venta_mujer[1]}
    dondetoy = "familias_venden"
    return render_to_response('encuestas/venta_organizada.html', RequestContext(request, locals()))

def get_vende_num(query, filtro):
    venden = novenden = 0
    for obj in query:
        n = obj.vendeproducto_set.filter(forma__in=filtro).count()
        if n != 0:
            venden += 1
        #n1 = obj.vendeproducto_set.filter(forma=5).count()
        #if n1 != 0:
        novenden = query.count() - venden
    return venden, novenden

def procesando_productos(request):
    encuestas = _query_set_filtrado(request)
    labels = {1: '% de familias procesando', 2: '% de familias que no procesan'}

    venta = get_proces_num(encuestas)
    venta_hombre = get_proces_num(encuestas.filter(sexo_jefe=1))
    venta_mujer = get_proces_num(encuestas.filter(sexo_jefe=2))

    total = sum(venta)
    total_hombre = sum(venta_hombre)
    total_mujer = sum(venta_mujer)

    dicc = {1: venta[0], 2: venta[1]}
    dicc_hombre = {1: venta_hombre[0], 2: venta_hombre[1]}
    dicc_mujer = {1: venta_mujer[0], 2: venta_mujer[1]}
    dondetoy = "procesando_prod"
    return render_to_response('encuestas/procesando_productos.html', RequestContext(request, locals()))

def get_proces_num(query):
    procesan = noprocesan = 0
    for obj in query:
        n = obj.productosprocesado_set.all().count()
        if n != 0:
            procesan += 1
    noprocesan = query.count() - procesan
    return procesan, noprocesan

def tecnologia_agricola(request):
    encuestas = _query_set_filtrado(request)
    labels = {1: u'% de familias que usan tecnología agricola para fertilizar'}

    venta = get_fam_organica(encuestas)
    venta_hombre = get_fam_organica(encuestas.filter(sexo_jefe=1))
    venta_mujer = get_fam_organica(encuestas.filter(sexo_jefe=2))

    total = sum(venta)
    total_hombre = sum(venta_hombre)
    total_mujer = sum(venta_mujer)

    dicc = {1: venta[0]}
    dicc_hombre = {1: venta_hombre[0]}
    dicc_mujer = {1: venta_mujer[0]}
    dondetoy = "tecnologia"
    return render_to_response('encuestas/tecnologia_agricola.html', RequestContext(request, locals()))

def get_fam_organica(query):
    counter = falso = 0
    for obj in query:
        subquery = obj.usotecnologia_set.all()
        n = subquery.filter(Q(granos=1) | Q(anuales=1) | Q(permanentes=1) | Q(pastos=1), tecnologia=3).count()
        n1 = subquery.filter(Q(granos=1) | Q(anuales=1) | Q(permanentes=1) | Q(pastos=1), tecnologia=4).count()
        if (n != 0 and n1 != 0) or n != 0 or n1 != 0:
            counter += 1
        else:
            falso += 1

    return counter, falso

def _hombre_mujer_dicc(ids, jefe=False):
    '''Funcion que por defecto retorna la cantidad de beneficiarios
    hombres y mujeres de una lista de ids. Si jefe=True, retorna los
    jefes de familia hombres y mujeres segun la lista de ids :D'''
    composicion_familia = Composicion.objects.filter(encuesta__id__in=ids)
    if jefe:
        '''1: Hombre, 2: Mujer, 3: Compartido'''
        dicc = {1: 0, 2: 0}
        for composicion in composicion_familia:
            #validar si el beneficiario es el jefe de familia
            if composicion.beneficio in [1, 3]:
                dicc[composicion.sexo] += 1
            elif composicion.beneficio == 2:
                if composicion.sexo_jefe in [1, 2]:
                    dicc[composicion.sexo_jefe] += 1
                else:
                    dicc[composicion.sexo] += 1

        return dicc

    return {
            'hombre': composicion_familia.filter(sexo=1).count(),
            'mujer': composicion_familia.filter(sexo=2).count()
            }

def _queryid_hombre_mujer(ids, flag=False):
    '''funcion que retorna las encuestas separadas por tipo de jefe,
    Hombre, Mujer y Compartido'''
    composicion_familia = Composicion.objects.filter(encuesta__id__in=ids)

    '''1: Hombre, 2: Mujer, 3: Compartido'''
    dicc = {1: [], 2: [], 3: [], 4:[]}
    for composicion in composicion_familia:
        #validar si el beneficiario es el jefe de familia
        if composicion.beneficio in [1, 3]:
            if not flag:
                dicc[composicion.sexo].append(composicion.encuesta.id)
            else:
                dicc[composicion.sexo].append(composicion.encuesta)
        else:
            if not flag:
                dicc[composicion.sexo_jefe].append(composicion.encuesta.id)
            else:
                dicc[composicion.sexo_jefe].append(composicion.encuesta)


    return dicc

def _order_dicc(dicc):
    return sorted(dicc.items(), key=lambda x: x[1], reverse=True)

#FUNCIONES UTILITARIAS PARA TODO EL SITIO
def saca_porcentajes(values):
    """sumamos los valores y devolvemos una lista con su porcentaje"""
    total = sum(values)
    valores_cero = [] #lista para anotar los indices en los que da cero el porcentaje
    for i in range(len(values)):
        porcentaje = (float(values[i])/total)*100
        values[i] = "%.2f" % porcentaje + '%'
    return values

def saca_porcentajes(dato, total, formato=True):
    '''Si formato es true devuelve float caso contrario es cadena'''
    if dato != None:
        try:
            porcentaje = (dato/float(total)) * 100 if total != None or total != 0 else 0
        except:
            return 0
        if formato:
            return porcentaje
        else:
            return '%.2f' % porcentaje
    else:
        return 0

def calcular_promedio(lista):
    n = len(lista)
    total_suma = sum(lista)
    try:
        return round(total_suma/n, 2)
    except:
        return 0

def calcular_mediana(lista):
    n = len(lista)
    lista = sorted(lista)

    #calcular si lista es odd or even
    if (n%2) == 1:
        try:
            index = (n+1)/2
        except:
            index = 0
        return lista[index-1]
    else:
        index_1 = (n/2)
        index_2 = index_1+1
        try:
            return calcular_promedio([lista[index_1-1], lista[index_2-1]])
        except:
            return 0
#Los puntos en el mapa
def obtener_lista(request):
    b = _queryset_filtrado_mapa(request)
    lista = []
    data = {}

    #for tuma in b:
    #    print u'sexoEncuesta: %s, sexoFamilia: %s' % (tuma.sexo_jefe, tuma.composicion_set.get(encuesta__id=tuma.id).sexo)

    for obj in b:
        key = 'hombres' if obj.composicion_set.get(encuesta__id=obj.id).sexo == 1 else 'mujeres'
        name = obj.comarca.municipio.nombre
        try:
            data[name][key] += 1
        except:
            if obj.comarca.municipio.latitud:
                data[name] = dict(hombres=0, mujeres=0,
                                  lon=float(obj.comarca.municipio.longitud),
                                  lat=float(obj.comarca.municipio.latitud),)
                data[name][key] += 1

    lista.append(data)
    return HttpResponse(simplejson.dumps(lista), mimetype='application/javascript')

# funcion para exportar spss datos
from medios.models import CHOICE_SEXO, CHOICE_DESCRIPCION, CHOICE_INMIGRACION, \
CHOICE_ACCESO, CHOICE_AREA, CHOICE_SINO
from calidad_vida.models import CHOICE_NO_ESTUDIA, Abastece
from produccion.models import CPeriodos, CPermanentes, CAnuales, CHortalizas, Ganado
from tecnologia.models import CHOICE_RIEGO, CHOICE_CSA, CHOICE_TECNOLOGIAS
from diversidad_alimentaria.models import Alimentos
from participacion_ciudadana.models import CHOICE_CIUDADANA, CHOICE_CIUDADANA_DOS, CHOICE_CIUDADANA_TRES
from genero.models import CHOICE_GENERO, CHOICE_ASPECTO
from ingresos.models import Ganados
#@session_required
def volcar_xls(request, modelo):
    encuestas = _query_set_filtrado(request)
    ayuda = modelo
    si_no = CHOICE_SINO
    descripcion = CHOICE_DESCRIPCION
    choice_inmigracion = CHOICE_INMIGRACION
    acceso_escuela = CHOICE_ACCESO
    no_estudia = CHOICE_NO_ESTUDIA
    abastece = Abastece.objects.all()
    tierra_area = CHOICE_AREA
    cultivos_periodos = CPeriodos.objects.all()
    cultivos_permanentes = CPermanentes.objects.all()
    cultivos_anuales = CAnuales.objects.all()
    cultivos_hortaliza = CHortalizas.objects.all()
    ganado_mayor = Ganado.objects.all()
    ingreso_periodo = CIPeriodos.objects.all()
    ingreso_permanente = CIPermanentes.objects.all()
    ingreso_estacionales = CIEstacionales.objects.all()
    ingreso_hortaliza = CIHortalizas.objects.all()
    ingreso_ganados = Ganados.objects.all()
    ingreso_procesados = PProcesado.objects.all()
    ingreso_ultimo = Productos.objects.all()
    ingreso_otros = OtrasActividades.objects.all()
    ingreso_vende_producto = ProductosPrincipales.objects.all()
    #...
    choice_riego = CHOICE_RIEGO
    choice_csa = CHOICE_CSA
    choice_tecnologia = CHOICE_TECNOLOGIAS
    choice_alimentos = Alimentos.objects.all()
    choice_ciudada = CHOICE_CIUDADANA
    choice_ciudada_dos = CHOICE_CIUDADANA_DOS
    choice_ciudada_tres = CHOICE_CIUDADANA_TRES
    choice_genero = CHOICE_GENERO
    choice_aspecto = CHOICE_ASPECTO

    resultados = []
    for encuesta in encuestas:
        filas = []
        filas.append(encuesta.fecha)
        filas.append(encuesta.municipio)
        filas.append(encuesta.comarca)
        filas.append(encuesta.beneficiario)
        filas.append(encuesta.encuestador)
        filas.append(encuesta.contraparte)
        if modelo == '1':
            composicion = encuesta.composicion_set.all()
            for obj in composicion:
                filas.append(obj.get_sexo_display)
                filas.append(obj.edad)
                filas.append(obj.get_estado_display)
                filas.append(obj.get_beneficio_display)
                filas.append(obj.get_relacion_display)
                filas.append(obj.get_sexo_jefe_display)
                filas.append(obj.num_familia)
                filas.append(int(obj.dependientes))
        if modelo == '2':
            escolaridad = encuesta.escolaridad_set.all()
            for obj in escolaridad:
                filas.append(obj.get_beneficia_display)
                filas.append(obj.get_conyugue_display)
        if modelo == '3':
            inmigracion = encuesta.inmigracion_set.all()
            for obj in inmigracion:
                filas.append(obj.get_inmigra_display)
                filas.append(obj.mujer)
                filas.append(obj.hombre)
        if modelo == '4':
            accesoescuela = encuesta.accesoescuela_set.all()
            for obj in accesoescuela:
                filas.append(obj.get_acceso_display)
                filas.append(obj.fem_estudia)
                filas.append(obj.fem_no_estudia)
                filas.append(obj.mas_estudia)
                filas.append(obj.mas_no_estudia)
        if modelo == '5':
            razonesnoestudia = encuesta.razonesnoestudia_set.all()
            for obj in razonesnoestudia:
                filas.append(obj.get_acceso_display)
                filas.append(obj.fem_no_estudia)
                filas.append(obj.mas_no_estudia)
        if modelo == '6':
            agua = encuesta.agua_set.all()
            for obj in agua:
                filas.append(obj.sistema)
                filas.append(obj.get_calidad_display)
                filas.append(obj.get_clorada_display)
                filas.append(obj.get_tiene_display)
                filas.append(obj.get_tiempo_display)
                filas.append(obj.get_techo_display)
                filas.append(obj.get_piso_display)
                filas.append(obj.get_paredes_display)
                filas.append(obj.get_servicio_display)
                filas.append(obj.cuartos)
                filas.append(obj.get_estado_display)
        if modelo == '7':
            tierra = encuesta.tierra_set.all()
            for obj in tierra:
                filas.append(obj.get_area_display)
                filas.append(obj.mujer)
                filas.append(obj.hombre)
                filas.append(obj.ambos)
                filas.append(obj.area_total)
        if modelo == '8':
            propiedad = encuesta.propiedad_set.all()
            for obj in propiedad:
                filas.append(obj.get_conflicto_display)
                filas.append(','.join(map(unicode, obj.ciclo.all().values_list(u'nombre',flat=True))))
                filas.append(','.join(map(unicode, obj.zonas.all().values_list(u'nombre',flat=True))))
        if modelo == '9':
            cultivosperiodos = encuesta.cultivosperiodos_set.all()
            for obj in cultivosperiodos:
                filas.append(obj.cultivos)
                filas.append(obj.primera)
                filas.append(obj.postrera)
                filas.append(obj.apante)
                filas.append(obj.p_primera)
                filas.append(obj.p_postrera)
                filas.append(obj.p_apante)
                filas.append(obj.productividad)
        if modelo == '10':
            cultivospermanentes = encuesta.cultivospermanentes_set.all()
            for obj in cultivospermanentes:
                filas.append(obj.cultivos)
                filas.append(obj.manzana)
                filas.append(obj.produccion)
                filas.append(obj.productividad)
        if modelo == '11':
            cultivosanuales = encuesta.cultivosanuales_set.all()
            for obj in cultivosanuales:
                filas.append(obj.cultivos)
                filas.append(obj.manzana)
                filas.append(obj.produccion)
                filas.append(obj.productividad)
        if modelo == '12':
            hortalizas = encuesta.hortalizas_set.all()
            for obj in hortalizas:
                filas.append(obj.cultivos)
                filas.append(obj.manzana)
                filas.append(obj.produccion)
                filas.append(obj.productividad)
        if modelo == '13':
            consumo = encuesta.consumodiario_set.all()
            for obj in consumo:
                filas.append(obj.maiz)
                filas.append(obj.frijol)
        if modelo == '14':
            limitaciones = encuesta.principallimitacion_set.all()
            for obj in limitaciones:
                filas.append(obj.opcion1)
                filas.append(obj.opcion2)
                filas.append(obj.opcion3)
        if modelo == '15':
            patio = encuesta.patiocultivada_set.all()
            for obj in patio:
                filas.append(obj.invierno)
                filas.append(obj.verano)
        if modelo == '16':
            arboles = encuesta.arboles_set.all()
            for obj in arboles:
                filas.append(obj.patio)
                filas.append(obj.otra)
        if modelo == '17':
            calidadpatio = encuesta.calidadpatio_set.all()
            for obj in calidadpatio:
                filas.append(obj.get_calidad_display)
        if modelo == '18':
            ganadomayor= encuesta.ganadomayor_set.all()
            for obj in ganadomayor:
                filas.append(obj.ganado)
                filas.append(obj.cantidad)
        if modelo == '19':
            principalesfuentes = encuesta.principalesfuentes_set.all()
            for obj in principalesfuentes:
                filas.append(','.join(map(unicode, obj.fuente.all().values_list(u'nombre',flat=True))))
        if modelo == '20':
            ingresoperiodo = encuesta.cultivosiperiodos_set.all()
            for obj in ingresoperiodo:
                filas.append(obj.cultivo)
                filas.append(obj.cuanto_primera)
                filas.append(obj.cuanto_postrera)
                filas.append(obj.cuanto_apante)
                filas.append(obj.precio_primera)
                filas.append(obj.precio_postrera)
                filas.append(obj.precio_apante)
                filas.append(obj.total)
        if modelo == '21':
            ingresopermanente = encuesta.cultivosipermanentes_set.all()
            for obj in ingresopermanente:
                filas.append(obj.cultivo)
                filas.append(obj.cuanto)
                filas.append(obj.precio)
                filas.append(obj.total)
        if modelo == '22':
            ingresoestacional = encuesta.cultivosiestacionales_set.all()
            for obj in ingresoestacional:
                filas.append(obj.cultivo)
                filas.append(obj.cuanto)
                filas.append(obj.precio)
                filas.append(obj.total)
        if modelo == '23':
            ingresohortaliza = encuesta.ihortalizas_set.all()
            for obj in ingresohortaliza:
                filas.append(obj.hortaliza)
                filas.append(obj.cuanto)
                filas.append(obj.precio)
                filas.append(obj.total)
        if modelo == '24':
            ingresopatio = encuesta.ingresopatio_set.all()
            for obj in ingresopatio:
                filas.append(obj.invierno)
                filas.append(obj.verano)
        if modelo == '25':
            ingresoganado = encuesta.ingresoganado_set.all()
            for obj in ingresoganado:
                filas.append(obj.ganado)
                filas.append(obj.vendidos)
                filas.append(obj.valor)
                filas.append(obj.total)
        if modelo == '26':
            ingresoprocesado = encuesta.productosprocesado_set.all()
            for obj in ingresoprocesado:
                filas.append(obj.producto)
                filas.append(obj.cantidad)
                filas.append(obj.monto)
        if modelo == '27':
            ingresoultimos = encuesta.lactios_set.all()
            for obj in ingresoultimos:
                filas.append(obj.producto)
                filas.append(obj.invierno_precio)
                filas.append(obj.cantidad_invi)
                filas.append(obj.verano_precio)
                filas.append(obj.cantidad_vera)
                filas.append(obj.total)
        if modelo == '28':
            otrosingresos = encuesta.otrosingresos_set.all()
            for obj in otrosingresos:
                filas.append(obj.actividad)
                filas.append(obj.mayo)
                filas.append(obj.junio)
                filas.append(obj.julio)
                filas.append(obj.agosto)
                filas.append(obj.septiembre)
                filas.append(obj.octubre)
                filas.append(obj.noviembre)
                filas.append(obj.diciembre)
                filas.append(obj.enero)
                filas.append(obj.febrero)
                filas.append(obj.marzo)
                filas.append(obj.abril)
                filas.append(obj.total)
        if modelo == '29':
            comercializar = encuesta.principalforma_set.all()
            for obj in comercializar:
                filas.append(obj.get_principal_display())
        if modelo == '30':
            vendeproducto = encuesta.vendeproducto_set.all()
            for obj in vendeproducto:
                filas.append(obj.principal)
                filas.append(obj.get_forma_display)
        if modelo == '31':
            riego = encuesta.riego_set.all()
            for obj in riego:
                filas.append(obj.get_respuesta_display)
                filas.append(obj.area)
        if modelo == '32':
            areaprotegida = encuesta.areaprotegida_set.all()
            for obj in areaprotegida:
                filas.append(obj.get_respuesta_display)
                filas.append(obj.cantidad)
        if modelo == '33':
            tecnologia = encuesta.usotecnologia_set.all()
            for obj in tecnologia:
                filas.append(obj.get_tecnologia_display)
                filas.append(obj.get_granos_display)
                filas.append(obj.get_anuales_display)
                filas.append(obj.get_permanentes_display)
                filas.append(obj.get_pastos_display)
        if modelo == '34':
            semilla = encuesta.semilla_set.all()
            for obj in semilla:
                filas.append(obj.get_maiz_display)
                filas.append(obj.get_frijol_display)
        if modelo == '35':
            diversidad = encuesta.diversidad_set.all()
            for obj in diversidad:
                filas.append(obj.alimento)
                filas.append(obj.get_respuesta_display)
        if modelo == '36':
            crisis = encuesta.crisis_set.all()
            for obj in crisis:
                filas.append(obj.get_escases_display)
                filas.append(obj.causa)
                filas.append(','.join(map(unicode, obj.enfrentar.all().values_list(u'nombre',flat=True))))
        if modelo == '37':
            credito = encuesta.accesocredito_set.all()
            for obj in credito:
                filas.append(','.join(map(unicode, obj.hombre.all().values_list(u'nombre',flat=True))))
                filas.append(','.join(map(unicode, obj.mujer.all().values_list(u'nombre',flat=True))))
                filas.append(','.join(map(unicode, obj.otro_hombre.all().values_list(u'nombre',flat=True))))
                filas.append(','.join(map(unicode, obj.otra_mujer.all().values_list(u'nombre',flat=True))))
        if modelo == '38':
            participacion = encuesta.participacion_set.all()
            for obj in participacion:
                filas.append(obj.get_organismo_display)
                filas.append(obj.get_respuesta_display)
        if modelo == '39':
            cpc = encuesta.participacioncpc_set.all()
            for obj in cpc:
                filas.append(obj.get_organismo_display)
                filas.append(obj.hombre)
                filas.append(obj.mujer)
                filas.append(obj.ambos)
        if modelo == '40':
            frecuencia = encuesta.frecuencia_set.all()
            for obj in frecuencia:
                filas.append(obj.get_organismo_display)
                filas.append(obj.get_respuesta_display)
        if modelo == '41':
            genero = encuesta.genero_set.all()
            for obj in genero:
                filas.append(obj.get_responsabilidades_display)
                filas.append(obj.get_respuesta_display)
        if modelo == '42':
            tomadecicion = encuesta.tomadecicion_set.all()
            for obj in tomadecicion:
                filas.append(obj.get_aspectos_display)
                filas.append(obj.get_respuesta_display)
        if modelo == '43':
            descripcion1 = encuesta.descripcion_set.all()
            for obj in descripcion1:
                filas.append(obj.get_descripcion_display)
                filas.append(obj.femenino)
                filas.append(obj.masculino)


        resultados.append(filas)

    dict = {'resultados':resultados, 'descripcion':descripcion,
            'choice_inmigracion':choice_inmigracion,'acceso_escuela':acceso_escuela,
            'no_estudia':no_estudia ,'tierra_area':tierra_area,
            'cultivos_periodos':cultivos_periodos,'cultivos_permanentes':cultivos_permanentes,
            'cultivos_anuales':cultivos_anuales, 'cultivos_hortaliza':cultivos_hortaliza,
            'ganado_mayor':ganado_mayor,'ingreso_periodo':ingreso_periodo,
            'ingreso_permanente':ingreso_permanente, 'ingreso_estacionales':ingreso_estacionales,
            'ingreso_hortaliza':ingreso_hortaliza, 'ingreso_ganados':ingreso_ganados,
            'ingreso_procesados':ingreso_procesados, 'ingreso_ultimo':ingreso_ultimo,
            'ingreso_otros':ingreso_otros, 'ingreso_vende_producto':ingreso_vende_producto,
            'choice_riego':choice_riego, 'choice_csa':choice_csa, 'choice_tecnologia':choice_tecnologia,
            'choice_alimentos':choice_alimentos, 'choice_ciudada':choice_ciudada,
            'choice_ciudada_dos':choice_ciudada_dos, 'choice_ciudada_tres':choice_ciudada_tres,
            'choice_genero':choice_genero, 'choice_aspecto':choice_aspecto, 'ayuda':ayuda,

    }
    return dict

def spss_xls(request, modela):
    varia = modela
    dict = volcar_xls(request, modelo=varia)
    return write_xls('spss.html', dict, 'spss.xls')

def write_xls(template_src, context_dict, filename):
    response = render_to_response(template_src, context_dict)
    response['Content-Disposition'] = 'attachment; filename='+filename
    response['Content-Type'] = 'application/vnd.ms-excel'
    response['Charset']='UTF-8'
    return response
