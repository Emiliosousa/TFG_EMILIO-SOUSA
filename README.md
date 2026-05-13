# ECPLICACION COMPLETA TODOS LOS NOTEBOOKS

Buenas profe. Te dejo un repaso rápido por encima de los 9 notebooks de la carpeta para que sepas qué hace cada uno sin tener que abrirlos. Están en `notebooks/` y se ejecutan en orden: el 01 y el 02 son obligatorios, del 03 al 09 ya son independientes pero todos tiran de los dos primeros.

**Aviso antes de empezar.** Como ya te comenté en las últimas tutorias, el CSV crudo tenía algunas filas con las cuotas locales y visitantes cruzadas, así un Real Madrid - Almería tenía la cuota del Almería como si fuera la del Madrid jajaj. Con ese bug me salían 9 temporadas positivas y el bankroll subía a varios millones de euros, que era ridículo. Cuando lo arreglé pasé a 1 sola temporada positiva. Y luego, ajustando bien filtros, ventana y limpiando el Elo, llegué a las 5 que tengo ahora. Era un bug de carga, no del modelo.

---

## 01_Datos.ipynb
Aquí monto el CSV final (`df_final_clean.csv`) a partir de los datos brutos de football-data, le añado los valores de mercado de Transfermarkt, los ratings FIFA, calculo el Elo a mano (K=30, +100 al que juega en casa), las rachas de los últimos 5 partidos y los enfrentamientos directos de los 3 últimos. Acaban siendo 14 variables y 5700 partidos, de 2010 a 2024. Las rachas las dejé en 5 porque con 3 era todo muy ruidoso (una lesión te cambiaba toda la racha)y con 10 ya se parecía demasiado al valor de mercado.El H2H lo puse a 3 porque cubre año y medio, que es lo que tarda una plantilla en cambiar bastante.

## 02_Modelo.ipynb
Entreno XGBoost con Optuna para que busque los mejores hiperparametros(50 intentos y semilla fija para que sea reproducible). Lo importante aquí es que la calibración la hago respetando el orden temporal, porque si no, el modelo acaba usando partidos del futuro para corregir el pasado y habria data leakage. Probé también la calibración sigmoide y pierde por bastante, así que me quedé con isotónica.

Una duda que tengo es que los hiperparámetros se buscan con datos del 2018 al 2023 y luego los aplico a todo el backtest (2012-2024). Para los primeros años son hiperparámetros del futuro. Lo correcto sería un doble walk-forward, pero tardaba una pecha en cargar y los resultados no cambiaban mucho. Lo dejo así y lo digo en la memoria.

## 03_Backtest.ipynb
El backtest principal. Voy temporada por temporada entrenando con las 5 anteriores y prediciendo la siguiente. Apuesto solo a victoria local en cuotas entre 1,40-1,70 y 2,00-2,50 (esos rangos los validé antes, son donde el modelo tiene más sentido). Quité empate y visitante porque en pruebas anteriores no daban nada. Apuesto cuando el valor esperado supera el 5% y tengo un "kill switch": si tras 15 apuestas la temporada va muy mal (la tasa de aciertos cae mucho por debajo de lo que decía el modelo), paro y no apuesto más ese año.

Resultado: 344 apuestas, 53,2% de aciertos, ROI +2,59% (paso de 1000 a 1089€), Kelly fraccional 1/4 -1,82% (1000 → 761€), 5 temporadas positivas de 13. Honestamente, el intervalo de confianza es bastante ancho y mete al cero dentro, así que no se puede decir con seguridad que el sistema gane de verdad. Pero al menos cierra en positivo.

Sobre el Kelly: probé fracciones del 5% al 50% y casi todas pierden con el bankroll real (el que va creciendo o decreciendo con cada apuesta). Solo el 33% y 50% son ligeramente positivas pero las caídas son brutales (más del 60% del bankroll abajo en algún momento). En este caso flat tiene más sentido que Kelly porque el edge es marginal y el modelo se confía un poco de más, y eso Kelly lo amplifica.

## 04_Simulaciones.ipynb
Aquí muevo los parámetros uno a uno para ver cómo cambia el resultado.
- **Umbral de valor esperado**: el mejor es 6% con +4,09%, después el 7% con +2,63% y el 5% (la base) con +2,59%. A partir del 8% se hunde porque te quedas con casi nada de muestra.
- **Fracción de Kelly**: lo que decía arriba, ninguna sale bien con el bankroll real.
- **Tamaño de ventana**: solo sliding 3 (+4,88%) y sliding 5 (+2,59%) salen positivas. El resto pierden. Sliding 3 puede ser sobreajuste (la mejor de 7 que probé), por eso me quedé con la 5 que es más estable.
- **Calibración**: la isotónica respetando el orden temporal le saca varios puntos a otras alternativas que probé.

## 05_Analisis.ipynb
Aquí hago una especie de analisis del backtest. Miro cómo de bien calibrado está el modelo año a año, cómo va por rango de cuota, si el rendimiento se concentra en algún mes, sesgos por tipo de apuesta y un test de significancia para ver si el resultado es real o azar. Lo más importante: 2019 es un desastre absoluto, 26,7% de aciertos cuando el modelo decía 63%, ROI -52%. Esa temporada sola se come unos 4-5 puntos del agregado. Por rango de cuota, el sistema funciona bien en [2,00-2,50) (que es donde están la mayoría de las apuestas).

## 06_Experimentos_Empate.ipynb
Aquí me obsesioné con el empate profe. La intuición era que si el modelo predice empate con cuota alta, debería haber valor. Pero la realidad es que el empate acierta más o menos el 26% del tiempo, que es lo mismo que dice la cuota implícita, así que no hay ventaja real. Probé 7 configuraciones y luego 13 sub-rangos de cuota con validación dentro y fuera de muestra. El único trozo que salía positivo de verdad era el rango X[3,70-4,50). En el filtro principal del 03 lo dejé fuera porque la muestra es pequeña, pero en el grid del 09 ese trozo sí emerge con fuerza.

Aviso: este notebook lo hice arrancando en 2015 en vez de en 2012, una inconsistencia que se me coló. Rehacerlo con 2012 no cambia las conclusiones cualitativas, así que lo dejé. Lo digo en la memoria.

## 07_Filtro_Improbables.ipynb
Dos filtros para descartar apuestas raras donde el modelo se entusiasma demasiado:
- **Filtro A** (probabilidad mínima del modelo): el mejor es 0,45 con +2,92%. 
- **Filtro B** (modelo/mercado): el mejor es 1,15 con +5,79% y 8 temporadas positivas de 13.

El filtro B es lo más útil del notebook. La idea es que si el modelo dice que un equipo gana con 45% pero el mercado dice 25%, lo más probable es que el modelo se haya pasado. Cortando esas apuestas mejora bastante. Aunque hay que tener cuidado: el umbral lo elegí mirando los mismos datos del backtest, así que tiene riesgo de estar adaptado a esos datos. Habría que validarlo en una temporada nueva por ejemplo con esta.

Las combinadas también las probé en su momento, pero al multiplicar cuotas, aunque aciertes más, la cuota cae tanto que el ROI se queda en cero. Vamos que no merecía la pena el seguro de añadir SEVILLA-EMPATE.

## 08_Media_Temporada.ipynb
Lo que me dijiste de re-entrenar el modelo a mitad de temporada (en enero) en vez de solo en agosto. La idea era aprovechar la primera vuelta para predecir mejor la segunda.

Resultado: el ROI agregado baja (de +2,59% a -0,37%), pero medio-temporada mejora a temporada-completa en 6 años de 13, sobre todo en años malos como 2014, 2015, 2019 y 2022 donde la mejora es de 15-19 puntos. Lo que pasa es que el kill switch del modelo completo corta a 15 apuestas en años malos y al re-empezar en enero, medio-temporada permite recuperar algo. Pero como el agregado sale peor y la complejidad sube, no lo adopté como configuración por defecto.

## 09_Grid_Search.ipynb
Aquí pruebo TODAS las combinaciones de los parámetros: 7 ventanas × 6 umbrales × 4 filtros × 4 ratios × 2 kill switches = 1344 combinaciones. Para que no tardara horas, pre-calculé las predicciones por (ventana, temporada) una sola vez, así solo tengo que aplicar filtros sobre dataframes ya usados. Compila en unos 5 minutos.

Validé in-sample 2012-2019 y luego lancé las mejores en out-of-sample 2020-2024 con un criterio estricto: solo cuentan como buenas si ganan en los dos periodos. De las 1344, 486 ganan in-sample, y solo 5 sobreviven out-of-sample. La mejor: ventana de 5, EV mínimo 10%, apostar solo al empate en cuotas 3,50-4,50, ratio máximo 1,15 y kill switch activo. ROI +18,55% sobre el periodo completo.

Lo curioso es que 4 de las 5 buenas apuestan SOLO al empate en ese rango. El nicho del empate que en el 06 parecía irrelevante, ajustado con un EV alto y filtro de ratio, sí emerge. La muestra de apuestas cada combinacion es muy pequeña, así que tampoco lo tomo como verdad absoluta, pero apunta a algo real.

---

## Sobre la IA
Profe, te aviso porque me parece justo: he usado IA para apoyarme en la parte de programar, sobre todo para refactorizar y limpiar funciones que iba escribiendo a trozos. Pero entendiendo lo que hacía y corrigiéndola cuando proponía cosas raras.

Cualquier duda me dices, un saludo y muchas gracias!
