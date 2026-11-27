select t.nombre,
       (to_regclass('paktai_edu.' || t.nombre) is not null) as existe,
       coalesce((select c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
                 where n.nspname='paktai_edu' and c.relname=t.nombre), false) as seguridad_por_fila
from (values ('seguimiento'),('seguimiento_etapas'),('evaluaciones'),('evaluacion_preguntas'),('evaluacion_resultados')) as t(nombre);
