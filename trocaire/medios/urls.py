from django.conf.urls.defaults import *
from django.conf import settings

urlpatterns = patterns('trocaire.medios.views',
    url(r'^$', 'index'),
    url(r'^consultar/$', 'consultar', name="consultar"),
    #para extrar los lugares
    url(r'^consultar/ajax/municipio/(?P<departamento>\d+)/$', 'get_municipios'),
    url(r'^consultar/ajax/comarca/(?P<municipio>\d+)/$', 'get_comarca'),
    url(r'^encuestas/generales/$', 'indicadores', name="indicadores"),
    url(r'^encuestas/datos-x-sexo/$', 'datos_sexo', name="datos_sexo"),
    url(r'^encuestas/agua-clorada/$', 'agua_clorada', name="agua_clorada"),
)
