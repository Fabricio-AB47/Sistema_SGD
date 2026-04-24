# Plantilla Integral Del Proceso De Autoevaluacion

## 1. Objetivo
Estandarizar la ejecucion, control y cierre del proceso de autoevaluacion para asegurar cumplimiento de tiempos, trazabilidad de decisiones y evidencias verificables en cada etapa.

## 2. Alcance
Aplica desde la aprobacion del ciclo de autoevaluacion hasta la recepcion formal por el responsable evaluador.

## 3. Roles Y Responsables
| Rol | Responsabilidad principal | Entregable de salida |
|---|---|---|
| Responsable de Calidad | Coordinar el proceso, validar cumplimiento metodologico | Plan de autoevaluacion difundido |
| Director o Jefe de Area | Asignar responsables, revisar avance, aprobar envio formal | Acta de aprobacion de envio |
| Subordinado Responsable de Carga | Cargar evidencias y metadatos completos | Evidencias registradas |
| Responsable Evaluador | Recibir y evaluar formalmente | Acuse de recepcion y estado en bandeja |
| Administrador del Sistema | Soporte de usuarios, roles, permisos y trazabilidad | Configuracion activa y auditoria |

## 4. Flujo Operativo Estandar
1. Aprobacion del ciclo de autoevaluacion.
2. Asignacion de responsables por area (director/jefe a subordinados).
3. Carga de informacion y evidencias por subordinados.
4. Revision de jefe para visto de avance (aprobacion parcial o devolucion).
5. Envio formal del proceso con aprobacion del director de area.
6. Recepcion por responsable evaluador.

## 5. Checklist Maestro De Ejecucion

### Etapa 1. Aprobacion Del Ciclo
- [ ] Ciclo creado con nombre, fecha inicio, fecha fin y estado inicial.
- [ ] Documento de autorizacion cargado y asociado al ciclo.
- [ ] Estado del ciclo actualizado a APROBADO.
- [ ] Usuario aprobador y fecha de aprobacion registrados.
- [ ] Acta o evidencia de aprobacion archivada.

### Etapa 2. Asignacion De Responsables
- [ ] Roles y permisos validados para director/jefe y subordinados.
- [ ] Responsable asignado por cada indicador/elemento.
- [ ] Matriz de asignacion publicada y comunicada.
- [ ] Confirmacion de recepcion por cada responsable asignado.

### Etapa 3. Carga De Informacion
- [ ] Evidencia cargada por cada elemento requerido.
- [ ] Metadatos completos (tipo, fecha, responsable, observaciones).
- [ ] Versionamiento inicial registrado.
- [ ] Estado de evidencia actualizado segun flujo operativo.
- [ ] Trazabilidad de auditoria verificada.

### Etapa 4. Revision De Jefatura
- [ ] Jefe revisa contenido, integridad y pertinencia de la evidencia.
- [ ] Se emite visto de avance o se genera observacion de subsanacion.
- [ ] Las observaciones quedan registradas con fecha y emisor.
- [ ] Si hay devolucion, se ejecuta correccion y reenvio.

### Etapa 5. Envio Formal Con Aprobacion Del Director
- [ ] Director de area valida consolidado del proceso.
- [ ] Director aprueba formalmente el envio.
- [ ] Registro de envio formal generado (usuario, fecha, comentario).
- [ ] Estado actualizado a enviado para evaluacion.

### Etapa 6. Recepcion Del Evaluador
- [ ] Responsable evaluador visualiza el proceso en bandeja.
- [ ] Recepcion formal registrada en el sistema.
- [ ] Estado de entrada a evaluacion confirmado.
- [ ] Observaciones iniciales del evaluador registradas (si aplica).

## 6. Criterios De Aceptacion Por Etapa
| Etapa | Criterio de aceptacion minimo | Evidencia requerida |
|---|---|---|
| Aprobacion del ciclo | Ciclo en estado APROBADO con documento de autorizacion | Registro de ciclo + documento |
| Asignacion de responsables | Todos los elementos tienen responsable asignado | Matriz de asignaciones |
| Carga de informacion | Evidencias y metadatos completos | Registros de evidencia |
| Revision de jefatura | Visto de avance o devolucion documentada | Bitacora de revision |
| Envio formal | Aprobacion del director y envio ejecutado | Acta y registro de envio |
| Recepcion evaluador | Recepcion registrada en bandeja | Acuse y estado de evaluacion |

## 7. Semaforo De Control
- Verde: etapa cerrada con evidencia completa.
- Amarillo: etapa en progreso sin bloqueo critico.
- Rojo: etapa bloqueada o vencida sin cierre.

## 8. Regla De Cierre Del Proceso
El proceso se considera CERRADO solo cuando:
1. Las 6 etapas estan en estado Cerrado.
2. No existen observaciones abiertas sin plan de accion.
3. Existe trazabilidad de aprobaciones y recepcion final.

## 9. Formato De Seguimiento Semanal (plantilla)
Usar la siguiente estructura para control:

| Semana | Etapa | Responsable | Fecha compromiso | Estado | Porcentaje | Semaforo | Evidencia | Bloqueo | Plan de accion |
|---|---|---|---|---|---:|---|---|---|---|
| 1 | Aprobacion del ciclo |  |  | No iniciado | 0 | Rojo |  |  |  |
| 1 | Asignacion de responsables |  |  | No iniciado | 0 | Rojo |  |  |  |
| 1 | Carga de informacion |  |  | No iniciado | 0 | Rojo |  |  |  |
| 1 | Revision de jefatura |  |  | No iniciado | 0 | Rojo |  |  |  |
| 1 | Envio formal |  |  | No iniciado | 0 | Rojo |  |  |  |
| 1 | Recepcion evaluador |  |  | No iniciado | 0 | Rojo |  |  |  |

## 10. Matriz RACI Del Proceso
| Actividad | Calidad | Director/Jefe | Subordinado | Evaluador | Admin Sistema |
|---|---|---|---|---|---|
| Aprobar ciclo | A | C | I | I | R |
| Asignar responsables | C | A/R | I | I | C |
| Cargar informacion | I | C | A/R | I | C |
| Revisar avance | C | A/R | C | I | I |
| Aprobar envio formal | C | A/R | I | I | I |
| Recibir proceso | I | I | I | A/R | I |

Leyenda RACI: R = Responsable ejecutor, A = Aprueba, C = Consultado, I = Informado.

## 11. Riesgos Frecuentes Y Mitigacion
| Riesgo | Impacto | Probabilidad | Mitigacion |
|---|---|---|---|
| Falta de aprobacion del ciclo en fecha | Alto | Media | Hito de control con alerta 48h antes |
| Asignaciones incompletas | Alto | Alta | Validacion obligatoria de cobertura por indicador |
| Evidencias sin metadatos | Medio | Alta | Regla de validacion previa al envio |
| Rechazo tardio por calidad de evidencia | Alto | Media | Revision interna de jefatura antes de envio formal |
| Retraso en recepcion evaluador | Medio | Media | Acuse obligatorio con SLA definido |

## 12. Indicadores De Proceso
1. Porcentaje de etapas cerradas = etapas cerradas / 6.
2. Cumplimiento de cronograma = hitos cerrados en fecha / hitos planificados.
3. Tasa de devolucion = evidencias devueltas / evidencias enviadas.
4. Tiempo promedio de cierre por etapa = suma dias por etapa / numero de etapas cerradas.

## 13. Minuta De Cierre Semanal (plantilla)
### Resumen
- Semana:
- Estado global (%):
- Semaforo global:

### Avances
-

### Bloqueos
-

### Decisiones
-

### Compromisos de la siguiente semana
- Responsable:
- Actividad:
- Fecha compromiso:
