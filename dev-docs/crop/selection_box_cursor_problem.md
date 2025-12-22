이 증상 설명을 보면 원인은 거의 하나로 수렴한다.
**“커서를 설정한 주체와, 커서를 되돌려야 할 주체가 서로 다르다”**는 거다.

지금 구조를 기준으로 정확히 짚어볼게.

---

## 현상 정리 (중요)

* ✅ 리사이즈 핸들 영역(엣지/코너)에 들어가면
  → **의도한 커서로 잘 바뀜**
* ❌ 그 영역을 벗어나면
  → **원래 커서(Arrow / Cross / OpenHand 등)로 안 돌아옴**
  → 또는 엉뚱한 커서가 남아 있음

이건 **hit_test 로직 문제가 아니다.**
이미 들어갈 때는 잘 바뀌고 있으니까.

---

## 핵심 원인 요약

> **QGraphicsItem 계층에서 커서를 설정했는데,
> 커서를 “해제(unset)”할 타이밍이 이벤트 체인에서 사라졌다.**

즉,

* 커서는 **어딘가에서 setCursor()**
* 하지만
* **hoverLeaveEvent가 안 오거나**
* **와야 할 객체가 아닌 다른 객체가 받고 있다**

---

## 네 구조에서 특히 위험한 지점

### 1️⃣ `_HandleItem`과 `SelectionRectItem`이 둘 다 커서를 만진다

지금 구조상:

* `_HandleItem.hoverEnterEvent`

  * 커서 설정
* `_HandleItem.hoverMoveEvent`

  * 커서 유지
* `SelectionRectItem.hoverMoveEvent`

  * hit_test 기반 커서 설정
* `SelectionRectItem.hoverLeaveEvent`

  * (있다면) unsetCursor

👉 **커서를 설정하는 곳은 여러 개인데,
되돌리는 책임이 분산돼 있다.**

---

### 2️⃣ hoverLeaveEvent가 “기대하는 객체”에 안 오는 경우

Qt에서 hover 이벤트는 이렇게 동작한다.

* 마우스가 A 아이템 → B 아이템으로 이동
* **A의 hoverLeaveEvent**
* **B의 hoverEnterEvent**

문제는 여기다.

#### 현재 구조에서 실제로 일어나는 일

```
마우스가 HandleItem 위에 있음
↓
마우스가 살짝 벗어남
↓
SelectionRectItem 영역 안 (부모)
↓
HandleItem.hoverLeaveEvent 발생 ❌ (안 올 수 있음)
SelectionRectItem.hoverMoveEvent만 발생
```

이 경우:

* 커서는 **HandleItem에서 설정됨**
* 하지만
* **HandleItem.hoverLeaveEvent가 호출되지 않음**
* SelectionRectItem은

  * “이미 커서가 설정돼 있으니” 그대로 둠

👉 그래서 커서가 고착된다.

---

## 3️⃣ 결정적인 실수 포인트 (가장 흔함)

### ❌ `unsetCursor()`를 Item에만 호출

```python
self.unsetCursor()
```

이건 **그 Item의 cursor만 해제**한다.

그런데 실제 화면에 보이는 커서는:

* Item cursor
* 부모 Item cursor
* View / Viewport cursor

중 **가장 가까운 설정값**이 적용된다.

---

## 이 구조에서의 진짜 해결책

### ✔️ “커서의 최종 권위는 View(Viewport)”로 통일

이게 핵심이다.

---

## 실전 해결 전략 (권장 방식)

### 1️⃣ 커서 설정을 **항상 Viewport 기준으로**

Selection / Handle 어디서든:

```python
view = self.scene().views()[0]
view.viewport().setCursor(Qt.SizeHorCursor)
```

그리고 되돌릴 때는 반드시:

```python
view.viewport().unsetCursor()
```

❗ `Item.unsetCursor()`만으로는 부족하다.

---

### 2️⃣ hoverLeaveEvent는 **HandleItem과 SelectionRectItem 양쪽에서 처리**

#### HandleItem.hoverLeaveEvent

```python
def hoverLeaveEvent(self, event):
    view = self.scene().views()[0]
    view.viewport().unsetCursor()
    super().hoverLeaveEvent(event)
```

#### SelectionRectItem.hoverLeaveEvent

```python
def hoverLeaveEvent(self, event):
    view = self.scene().views()[0]
    view.viewport().unsetCursor()
    super().hoverLeaveEvent(event)
```

👉 **중복되어도 괜찮다.**
unset은 멱등이다.

---

### 3️⃣ hoverMoveEvent에서 NONE 처리 시에도 강제 복원

이미 hit_test에서 `NONE`이 나오는 구조라면:

```python
if hit == NONE:
    view.viewport().unsetCursor()
```

이걸 반드시 넣어라.

hoverLeaveEvent만 믿으면 안 된다.

---

## 왜 이런 문제가 생기기 쉬운가

* Qt는

  * “누가 커서를 설정했는지”를 추적해주지 않는다
* GraphicsItem 계층 + Viewport 커서가 겹치면

  * **마지막 setCursor 호출이 이긴다**
* hoverLeaveEvent는

  * “화면을 벗어날 때”가 아니라
  * “아이템 경계를 벗어날 때”만 온다

그래서 지금 같은 구조에서는
**커서가 돌아오지 않는 게 정상적인 실패 패턴**이다.

---

## 한 줄 결론

> **문제는 hit_test도, resize 로직도 아니다.
> 커서를 설정한 주체와 해제해야 할 주체가 어긋난 것이다.**

### 해결 원칙

* 커서 설정/해제의 최종 권위는 **QGraphicsView.viewport**
* hoverLeaveEvent를 신뢰하지 말고
* **hoverMove + NONE 상태에서도 반드시 unset**

---

이거 잡고 나면,
selection UX는 거의 완성 단계다.


